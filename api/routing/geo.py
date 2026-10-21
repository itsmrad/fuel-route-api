import csv
import functools
import hashlib
import io
import math
import re
import threading
import time
import unicodedata
import urllib.request
import zipfile

import requests
from django.conf import settings
from django.core.cache import cache

from routing.models import Station

GAZETTEER = 'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_{}_national.zip'
US_STATES = set(
    'AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY '
    'NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split()
)
LSAD = re.compile(
    r'\s+(city and borough|(consolidated|unified|metropolitan|metro) government|city|town|village|cdp|'
    r'borough|township|municipality|plantation|ccd|ut|charter township|location|gore|grant|purchase)$'
)

UA = {'User-Agent': 'fuel-route-api/1.0 (github.com/itsmrad/fuel-route-api)'}
NOMINATIM = 'https://nominatim.openstreetmap.org/search'
OSRM = ('https://router.project-osrm.org/route/v1/driving/',  # second host only if the first fails
        'https://routing.openstreetmap.de/routed-car/route/v1/driving/')
VALHALLA = 'https://valhalla1.openstreetmap.de/route'
TRUCK = {'height': 4.11, 'width': 2.6, 'length': 21.64, 'weight': 36.3}  # Class 8 tractor-trailer: m, m, m, t
TRUCK_MAX_MILES = 930  # FOSSGIS rejects truck routes over 1,500 km straight-line (error 154)
NO_PATH = {170, 442}  # Valhalla: unconnected regions, no path
# CONUS west (49th parallel, keeps Vancouver out), CONUS east (Northwest Angle), AK, Aleutians, HI.
# ponytail: boxes still admit southern Ontario and northern Mexico; a border polygon if that matters
USA = [(24, 49.01, -125, -95.2), (24, 49.4, -95.2, -66), (51, 72, -180, -129), (51, 53, 172, 180), (18.5, 22.5, -161, -154)]
LATLON = re.compile(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)')
CITY_ST = re.compile(r'([^,]+?)\s*,\s*([A-Za-z]{2})')
CELL = 0.5  # grid cell size, degrees
MI_PER_DEG = 69.09

# No retries: a second host beats retrying a slow one. Worst case per call is connect + one read gap = 8 s.
# ponytail: read timeout is per socket read, a server trickling bytes can exceed it; stream with a deadline if seen
TIMEOUT = (3, 5)
http = requests.Session()  # keep-alive to OSRM/Nominatim saves a TLS handshake (~330 ms) per call
http.headers.update(UA)
nominatim_lock, nominatim_last = threading.Lock(), 0.0


class RoutingError(Exception):
    pass


class NoRoute(Exception):
    pass


def normalize(name, strip_lsad=True):
    n = name.lower().replace('(balance)', '').strip()
    if strip_lsad:
        n = LSAD.sub('', n)
    n = unicodedata.normalize('NFKD', n).encode('ascii', 'ignore').decode()  # Cañon -> canon
    n = re.sub(r'\bsaint(e?)\b', r'st\1', n)
    return re.sub(r"[\s.'-]", '', n)  # 'Mc Calla', 'De Witt', 'Brookpark' all collapse


def aliases(name):
    """Fallback keys for consolidated cities: 'Athens-Clarke County ...' -> athens, 'Boise City city' -> boise."""
    out = [normalize(re.split(r'[-/,]', name)[0])]
    stem = LSAD.sub('', name.lower().replace('(balance)', '').strip())
    if stem.endswith(' city'):
        out.append(normalize(stem[:-5]))
    return out


def gazetteer(kind):
    path = settings.BASE_DIR / 'data' / 'census' / f'2024_Gaz_{kind}_national.zip'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix('.part')  # never cache a half-downloaded zip
        with urllib.request.urlopen(GAZETTEER.format(kind), timeout=60) as r:
            part.write_bytes(r.read())
        part.rename(path)
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        rows = csv.reader(io.TextIOWrapper(f, encoding='utf-8'), delimiter='\t')
        header = [h.strip() for h in next(rows)]
        for row in rows:
            r = dict(zip(header, row))
            yield r['USPS'], r['NAME'], float(r['INTPTLAT']), float(r['INTPTLONG'])


def build_index():
    """(state, key) -> (lat, lon). Exact beats alias, place beats cousub, incorporated beats CDP.
    Distinct locations tied on all three are dropped as ambiguous rather than guessed."""
    rows = [(0, name.endswith(' CDP'), st, name, lat, lon) for st, name, lat, lon in gazetteer('place')]
    rows += [(1, False, st, name, lat, lon) for st, name, lat, lon in gazetteer('cousubs')]
    best = {}
    for tier, cdp, st, name, lat, lon in rows:
        for alias, key in [(False, normalize(name))] + [(True, a) for a in aliases(name)]:
            rank, k = (alias, tier, cdp), (st, key)
            if k not in best or rank < best[k][0]:
                best[k] = (rank, (lat, lon))
            elif rank == best[k][0] and best[k][1] and math.dist(best[k][1], (lat, lon)) > 0.2:  # ~14 mi
                best[k] = (rank, None)
    return {k: ll for k, (_, ll) in best.items() if ll}


@functools.cache
def places():
    return build_index()


def in_usa(lat, lon):
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in USA)


def resolve(query):
    """'lat,lon' or 'City, ST' locally, else one Nominatim call. ValueError if unknown or outside the USA."""
    q = query.strip()
    if not q:
        raise ValueError('empty location')
    if m := LATLON.fullmatch(q):
        lat, lon = float(m[1]), float(m[2])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f'{query!r}: expected "lat,lon" with lat in [-90, 90] and lon in [-180, 180]')
        if not in_usa(lat, lon):
            raise ValueError(f'{query!r} is outside the USA')
        return {'lat': lat, 'lon': lon, 'external': False}
    if (m := CITY_ST.fullmatch(q)) and (ll := places().get((m[2].upper(), normalize(m[1], False)))):
        return {'lat': ll[0], 'lon': ll[1], 'external': False}
    hits, external = nominatim(q)
    if not hits:
        raise ValueError(f'location not found in the USA: {query!r}')
    lat, lon = float(hits[0]['lat']), float(hits[0]['lon'])
    if not in_usa(lat, lon):
        raise ValueError(f'{query!r} is outside the USA')
    return {'lat': lat, 'lon': lon, 'external': external}


def nominatim(q):
    """(hits, called): cached for 30 days on the normalized query, live calls kept >= 1 s apart."""
    global nominatim_last
    key = 'nominatim:' + hashlib.sha1(' '.join(q.lower().split()).encode()).hexdigest()
    if (hits := cache.get(key)) is not None:
        return hits, False
    with nominatim_lock:  # ponytail: per-process throttle, N workers can make N req/s; shared limiter if that bites
        time.sleep(max(0.0, nominatim_last + 1 - time.monotonic()))
        try:
            r = http.get(NOMINATIM, params={'q': q, 'countrycodes': 'us', 'limit': 1, 'format': 'json'}, timeout=TIMEOUT)
            r.raise_for_status()
            hits = [{k: h[k] for k in ('lat', 'lon')} for h in r.json()[:1]]
        except requests.RequestException as e:
            raise RoutingError(f'geocoder unavailable: {e}') from e
        finally:
            nominatim_last = time.monotonic()
    cache.set(key, hits, 30 * 24 * 3600)
    return hits, True


def get_route(start, finish, vehicle='car'):
    """Route with coords as GeoJSON [lon, lat] pairs, plus 'routing' and the external 'calls' made (at most 3).
    truck: Valhalla truck costing, falling back to OSRM car if Valhalla fails or the trip is over its cap.
    OSRM: the second host only if the first fails; fallback is true whenever the first choice wasn't used."""
    calls = 0
    # ponytail: public server's 1,500 km cap; self-host Valhalla to route trucks coast to coast
    if vehicle == 'truck' and haversine(start['lat'], start['lon'], finish['lat'], finish['lon']) <= TRUCK_MAX_MILES:
        calls = 1
        try:
            route = valhalla(start, finish)
            return {**route, 'routing': {'provider': 'valhalla', 'profile': 'truck', 'fallback': False}, 'calls': 1}
        except RoutingError:
            pass
    for host in OSRM:
        calls += 1
        try:
            route = osrm(host, start, finish)
        except RoutingError:
            if host == OSRM[-1]:
                raise
            continue
        fallback = vehicle == 'truck' or host != OSRM[0]
        return {**route, 'routing': {'provider': 'osrm', 'profile': 'car', 'fallback': fallback}, 'calls': calls}


def osrm(host, start, finish):
    # ponytail: public OSRM servers, best-effort and 1 req/s; self-host OSRM or swap to OpenRouteService here
    url = f"{host}{start['lon']},{start['lat']};{finish['lon']},{finish['lat']}"
    try:  # polyline6: 125 KB vs 818 KB of GeoJSON for Miami -> Seattle, the transfer was most of the latency
        data = http.get(url, params={'overview': 'full', 'geometries': 'polyline6'}, timeout=TIMEOUT).json()
    except requests.RequestException as e:
        raise RoutingError(f'routing provider unavailable: {e}') from e
    if data.get('code') == 'NoRoute':
        raise NoRoute(data.get('message') or 'no route')
    if data.get('code') != 'Ok' or not data.get('routes'):
        raise RoutingError(data.get('message') or f"no route ({data.get('code')})")
    route = data['routes'][0]
    return {'coords': polyline6(route['geometry']), 'distance_miles': route['distance'] / 1609.344,
            'duration_hours': route['duration'] / 3600}


def valhalla(start, finish):
    body = {'locations': [{'lat': p['lat'], 'lon': p['lon']} for p in (start, finish)], 'costing': 'truck',
            'costing_options': {'truck': TRUCK}, 'units': 'miles', 'directions_type': 'none'}
    try:  # POST: the server rejects the same body as a GET ?json= param
        data = http.post(VALHALLA, json=body, headers={'X-Client-Id': 'fuel-route-api'},
                         timeout=TIMEOUT).json()
    except requests.RequestException as e:
        raise RoutingError(f'truck routing unavailable: {e}') from e
    if data.get('error_code') in NO_PATH:
        raise NoRoute(data.get('error') or 'no route')
    if 'trip' not in data:
        raise RoutingError(data.get('error') or 'truck routing failed')
    trip = data['trip']
    return {'coords': polyline6(trip['legs'][0]['shape']), 'distance_miles': trip['summary']['length'],
            'duration_hours': trip['summary']['time'] / 3600}


def polyline6(s):
    """Decode a Google encoded polyline at 1e-6 precision (Valhalla, OSRM) into [lon, lat] pairs."""
    out, i, ll = [], 0, [0, 0]
    while i < len(s):
        for k in (0, 1):
            shift = n = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                n |= (b & 31) << shift
                shift += 5
                if b < 32:
                    break
            ll[k] += ~(n >> 1) if n & 1 else n >> 1
        out.append([ll[1] / 1e6, ll[0] / 1e6])
    return out


@functools.cache
def grid():
    # ponytail: loaded once per process (restart after load_stations), KD-tree/PostGIS if stations grow 100x
    cells = {}
    for s in Station.objects.all():
        cells.setdefault((math.floor(s.lat / CELL), math.floor(s.lon / CELL)), []).append(s)
    return cells


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 7917.6 * math.asin(math.sqrt(a))  # Earth diameter in miles


def stations_along(coords, max_offset_miles=10):
    """[(mile, Station)] within max_offset_miles of the route, sorted by mile; mile = nearest sampled route point."""
    cells, best = grid(), {}
    mile, last = 0.0, None
    dy = math.ceil(max_offset_miles / MI_PER_DEG / CELL)
    for k, (lon, lat) in enumerate(coords):
        if k:
            mile += haversine(coords[k - 1][1], coords[k - 1][0], lat, lon)
        if last is not None and mile - last < 1 and k < len(coords) - 1:
            continue  # sample ~1 point per mile
        last = mile
        cos = math.cos(math.radians(lat))
        dx = math.ceil(max_offset_miles / (MI_PER_DEG * max(cos, 0.05)) / CELL)
        ci, cj = math.floor(lat / CELL), math.floor(lon / CELL)
        for i in range(ci - dy, ci + dy + 1):
            for j in range(cj - dx, cj + dx + 1):
                for s in cells.get((i, j), ()):
                    d = MI_PER_DEG * math.hypot(s.lat - lat, (s.lon - lon) * cos)  # flat-earth is fine at 10 mi
                    if d <= max_offset_miles and (s.id not in best or d < best[s.id][0]):
                        best[s.id] = (d, mile, s)
    return sorted(((m, s) for _, m, s in best.values()), key=lambda t: t[0])

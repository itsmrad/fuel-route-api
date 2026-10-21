import csv
import io
import re
import unicodedata
import urllib.request
import zipfile
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

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
        urllib.request.urlretrieve(GAZETTEER.format(kind), part)
        part.rename(path)
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        rows = csv.reader(io.TextIOWrapper(f, encoding='utf-8'), delimiter='\t')
        header = [h.strip() for h in next(rows)]
        for row in rows:
            r = dict(zip(header, row))
            yield r['USPS'], r['NAME'], float(r['INTPTLAT']), float(r['INTPTLONG'])


def build_index():
    rows = [r for kind in ('place', 'cousubs') for r in gazetteer(kind)]
    index = {}
    for st, name, lat, lon in rows:  # exact names first: places win over cousubs
        index.setdefault((st, normalize(name)), (lat, lon))
    for st, name, lat, lon in rows:
        for a in aliases(name):
            index.setdefault((st, a), (lat, lon))
    return index


class Command(BaseCommand):
    help = 'Load fuel-prices.csv into Station, geocoded to city centroids via the Census Gazetteer.'

    def handle(self, *args, **opts):
        with open(settings.BASE_DIR / 'data' / 'fuel-prices.csv', newline='') as f:
            rows = list(csv.DictReader(f))

        best = {}
        for r in rows:
            if r['State'].strip() not in US_STATES:
                continue
            sid, price = int(r['OPIS Truckstop ID']), Decimal(r['Retail Price'])
            if sid not in best or price < best[sid][0]:
                best[sid] = (price, r)

        index = build_index()
        stations, unmatched = [], []
        for sid, (price, r) in best.items():
            city, state = r['City'].strip(), r['State'].strip()
            # unstripped first so 'Junction City' never falls to a place named 'Junction'
            ll = index.get((state, normalize(city, False))) or index.get((state, normalize(city)))
            if ll is None:
                unmatched.append(f'{city}, {state}')
                continue
            stations.append(Station(
                opis_id=sid, name=r['Truckstop Name'].strip(), address=r['Address'].strip(),
                city=city, state=state, price=price, lat=ll[0], lon=ll[1],
            ))

        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create(stations)

        self.stdout.write(
            f'rows read: {len(rows)}\nunique US stations: {len(best)}\n'
            f'matched: {len(stations)} ({len(stations) / len(best):.1%})\nunmatched: {len(unmatched)}'
        )
        if unmatched:
            self.stdout.write('first unmatched: ' + '; '.join(sorted(set(unmatched))[:20]))

import functools
import hashlib
import math
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.defaults import page_not_found

from routing import geo
from routing.optimizer import STOP_PENALTY, Unreachable, plan_fuel_stops

RANGE_MILES = 500
MAX_ROUTE_POINTS = 5000  # ~150 KB of coordinates for NYC->LA


def plan(start_q, finish_q, stop_penalty=STOP_PENALTY):
    """(result, external calls made). Cached on normalized input, so a repeat costs 0 calls."""
    norm = ' '.join(start_q.lower().split()) + '|' + ' '.join(finish_q.lower().split()) + f'|{stop_penalty!r}'
    key = 'route:' + hashlib.sha1(norm.encode()).hexdigest()
    if (hit := cache.get(key)) is not None:
        return hit, 0
    start, finish = geo.resolve(start_q), geo.resolve(finish_q)
    route = geo.get_route(start, finish)
    fuel = plan_fuel_stops([(m, s.price, s) for m, s in geo.stations_along(route['coords'])],
                           route['distance_miles'], range_miles=RANGE_MILES, stop_penalty=stop_penalty)
    coords = route['coords']
    # ponytail: keep every Nth point for the response only; Douglas-Peucker if the line looks jagged when zoomed in
    step = math.ceil(len(coords) / MAX_ROUTE_POINTS)
    line = coords[::step] + ([coords[-1]] if (len(coords) - 1) % step else [])
    result = {
        'start': {'query': start_q, 'lat': round(start['lat'], 4), 'lon': round(start['lon'], 4)},
        'finish': {'query': finish_q, 'lat': round(finish['lat'], 4), 'lon': round(finish['lon'], 4)},
        'distance_miles': round(route['distance_miles'], 1),
        'duration_hours': round(route['duration_hours'], 1),
        'fuel_stops': [{
            'mile': st['mile'], 'name': s.name, 'address': s.address, 'city': s.city, 'state': s.state,
            'lat': round(s.lat, 4), 'lon': round(s.lon, 4),
            'price': st['price'], 'gallons': st['gallons'], 'cost': st['cost'],
        } for st in fuel['stops'] for s in [st['payload']]],
        'total_gallons_purchased': fuel['total_gallons'],
        'total_fuel_cost': fuel['total_cost'],
        'cost_of_fuel_consumed': fuel['cost_of_fuel_consumed'],
        'stop_penalty': stop_penalty,
        'route': {'type': 'LineString', 'coordinates': [[round(x, 5), round(y, 5)] for x, y in line]},
    }
    cache.set(key, result)
    return result, 1 + start['external'] + finish['external']


def error(status, code, detail):
    return JsonResponse({'error': code, 'detail': detail}, status=status)


def api_get(view):
    """GET only, JSON 405 otherwise. csrf_exempt so a POST gets that 405, not CSRF's HTML 403."""
    @csrf_exempt
    @functools.wraps(view)
    def wrapped(request):
        if request.method not in ('GET', 'HEAD'):
            r = error(405, 'method_not_allowed', 'Only GET is supported.')
            r['Allow'] = 'GET, HEAD'
            return r
        return view(request)
    return wrapped


def plan_for(request):
    """(result, None) or (None, JSON error response) for the request's start/finish/stop_penalty."""
    start, finish, penalty = (request.GET.get(k, '').strip() for k in ('start', 'finish', 'stop_penalty'))
    if not start or not finish:
        return None, error(400, 'missing_parameter', 'Both "start" and "finish" are required.')
    try:
        penalty = float(penalty) if penalty else STOP_PENALTY
        if not 0 <= penalty < math.inf:
            raise ValueError
    except ValueError:
        return None, error(400, 'invalid_parameter', '"stop_penalty" must be a number >= 0 (USD per stop).')
    try:
        result, calls = plan(start, finish, penalty)
    except ValueError as e:
        return None, error(400, 'unknown_location', f'Could not resolve to a US location: {e}')
    except Unreachable as e:
        a, b = e.gap_start_mile, e.gap_end_mile
        return None, error(422, 'unreachable', f'No fuel station between mile {a:.1f} and mile {b:.1f} '
                                               f'({b - a:.1f} mi gap, range is {RANGE_MILES} mi).')
    except geo.RoutingError as e:
        return None, error(502, 'routing_provider_error', str(e))
    query = urlencode({'start': start, 'finish': finish, 'stop_penalty': penalty})
    result['start']['query'], result['finish']['query'] = start, finish  # cache hit may have other spelling
    result['map_url'] = request.build_absolute_uri(f"{reverse('route_map')}?{query}")
    result['external_api_calls'] = calls
    return result, None


@api_get
def route_api(request):
    result, err = plan_for(request)
    return err or JsonResponse(result)


@api_get
def route_map(request):
    if not request.GET.get('start') and not request.GET.get('finish'):
        return render(request, 'routing/map.html', {'default_penalty': STOP_PENALTY})  # empty demo form
    result, err = plan_for(request)
    return err or render(request, 'routing/map.html', {'plan': result, 'default_penalty': STOP_PENALTY})


@api_get
def openapi(request):
    path = settings.BASE_DIR / 'openapi.yaml'
    if not path.exists():
        return error(404, 'not_found', 'openapi.yaml is not deployed.')
    return FileResponse(path.open('rb'), content_type='application/yaml')


def not_found(request, exception=None):
    if request.path.startswith('/api/'):
        return error(404, 'not_found', f'No endpoint at {request.path}')
    return page_not_found(request, exception)


def server_error(request):
    return error(500, 'server_error', 'Internal server error.')

import functools
import math
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.defaults import page_not_found

from routing import geo
from routing.optimizer import STOP_PENALTY, Unreachable, plan_fuel_stops

RANGE_MILES = 500
MAX_ROUTE_POINTS = 5000  # ~104 KB response for NYC->LA


def leg(start, finish, vehicle='car'):
    """(route, routing calls made). Cached on vehicle + resolved coords, so spelling and stop_penalty never re-route."""
    a, b = (f"{p['lat']:.4f},{p['lon']:.4f}" for p in (start, finish))
    if a == b:
        here = [round(start['lon'], 5), round(start['lat'], 5)]
        return {'distance_miles': 0.0, 'duration_hours': 0.0, 'line': [here, here], 'corridor': [],
                'routing': None}, 0
    key = f'leg:{vehicle}:{a};{b}'
    if (hit := cache.get(key)) is not None:
        return hit, 0
    route = geo.get_route(start, finish, vehicle)
    coords = route['coords']
    # ponytail: keep every Nth point for the response only; Douglas-Peucker if the line looks jagged when zoomed in
    step = math.ceil(len(coords) / MAX_ROUTE_POINTS)
    line = coords[::step] + ([coords[-1]] if (len(coords) - 1) % step else [])
    result = {
        'distance_miles': route['distance_miles'],
        'duration_hours': route['duration_hours'],
        'routing': route['routing'],
        'line': [[round(x, 5), round(y, 5)] for x, y in line],
        'corridor': [(m, s.price, (s.name, s.address, s.city, s.state, s.lat, s.lon))
                     for m, s in geo.stations_along(coords)],
    }
    cache.set(key, result, 600 if route['calls'] > 1 else DEFAULT_TIMEOUT)  # retry Valhalla soon after an outage
    return result, route['calls']


def plan(start_q, finish_q, stop_penalty=STOP_PENALTY, vehicle='car'):
    """(result, external calls made). Only the optimizer runs on a cached route."""
    start, finish = geo.resolve(start_q), geo.resolve(finish_q)
    route, calls = leg(start, finish, vehicle)
    fuel = plan_fuel_stops(route['corridor'], route['distance_miles'], range_miles=RANGE_MILES,
                           stop_penalty=stop_penalty)
    return {
        'start': {'query': start_q, 'lat': round(start['lat'], 4), 'lon': round(start['lon'], 4)},
        'finish': {'query': finish_q, 'lat': round(finish['lat'], 4), 'lon': round(finish['lon'], 4)},
        'distance_miles': round(route['distance_miles'], 1),
        'duration_hours': round(route['duration_hours'], 1),
        'routing': route['routing'],
        'fuel_stops': [{
            'mile': st['mile'], 'name': name, 'address': address, 'city': city, 'state': state,
            'lat': round(lat, 4), 'lon': round(lon, 4),
            'price': st['price'], 'gallons': st['gallons'], 'cost': st['cost'],
        } for st in fuel['stops'] for name, address, city, state, lat, lon in [st['payload']]],
        'total_gallons_purchased': fuel['total_gallons'],
        'total_fuel_cost': fuel['total_cost'],
        'cost_of_fuel_consumed': fuel['cost_of_fuel_consumed'],
        'stop_penalty': stop_penalty,
        'route': {'type': 'LineString', 'coordinates': route['line']},
    }, calls + start['external'] + finish['external']


def error(status, code, detail):
    return JsonResponse({'error': code, 'detail': detail}, status=status)


def api_get(view):
    """GET only, JSON 405 otherwise."""
    @functools.wraps(view)
    def wrapped(request):
        if request.method not in ('GET', 'HEAD'):
            r = error(405, 'method_not_allowed', 'Only GET is supported.')
            r['Allow'] = 'GET, HEAD'
            return r
        return view(request)
    return wrapped


def plan_for(request):
    """(result, None) or (None, JSON error response) for the request's start/finish/stop_penalty/vehicle."""
    start, finish, penalty, vehicle = (request.GET.get(k, '').strip()
                                       for k in ('start', 'finish', 'stop_penalty', 'vehicle'))
    vehicle = vehicle or 'car'
    if not start or not finish:
        return None, error(400, 'missing_parameter', 'Both "start" and "finish" are required.')
    try:
        penalty = float(penalty) if penalty else STOP_PENALTY
        if not 0 <= penalty < math.inf:
            raise ValueError
    except ValueError:
        return None, error(400, 'invalid_parameter', '"stop_penalty" must be a number >= 0 (USD per stop).')
    if vehicle not in ('car', 'truck'):
        return None, error(400, 'invalid_parameter', '"vehicle" must be "car" or "truck".')
    try:
        result, calls = plan(start, finish, penalty, vehicle)
    except ValueError as e:
        return None, error(400, 'unknown_location', f'Could not resolve to a US location: {e}')
    except Unreachable as e:
        a, b = e.gap_start_mile, e.gap_end_mile
        return None, error(422, 'unreachable', f'No fuel station between mile {a:.1f} and mile {b:.1f} '
                                               f'({b - a:.1f} mi gap, range is {RANGE_MILES} mi).')
    except geo.NoRoute:
        return None, error(422, 'no_route', 'No driving route between start and finish '
                                            '(for example Hawaii to the mainland).')
    except geo.RoutingError as e:
        return None, error(502, 'routing_provider_error', str(e))
    query = urlencode({'start': start, 'finish': finish, 'stop_penalty': penalty, 'vehicle': vehicle})
    result['map_url'] = request.build_absolute_uri(f"{reverse('route_map')}?{query}")
    result['external_api_calls'] = calls
    return result, None


@api_get
def route_api(request):
    result, err = plan_for(request)
    return err or JsonResponse(result)


@api_get
def route_map(request):
    given = [request.GET.get(k, '').strip() for k in ('start', 'finish')]
    if not all(given):  # empty demo form, or a half-filled one
        error = 'Both start and finish are required.' if any(given) else None
        return render(request, 'routing/map.html', {'default_penalty': STOP_PENALTY, 'error': error},
                      status=400 if error else 200)
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

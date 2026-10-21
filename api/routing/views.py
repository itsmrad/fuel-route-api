import hashlib
import math
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from routing import geo
from routing.optimizer import Unreachable, plan_fuel_stops

RANGE_MILES = 500
MAX_ROUTE_POINTS = 5000  # ~150 KB of coordinates for NYC->LA


def plan(start_q, finish_q):
    """(result, external calls made). Cached on normalized input, so a repeat costs 0 calls."""
    norm = ' '.join(start_q.lower().split()) + '|' + ' '.join(finish_q.lower().split())
    key = 'route:' + hashlib.sha1(norm.encode()).hexdigest()
    if (hit := cache.get(key)) is not None:
        return hit, 0
    start, finish = geo.resolve(start_q), geo.resolve(finish_q)
    route = geo.get_route(start, finish)
    fuel = plan_fuel_stops([(m, s.price, s) for m, s in geo.stations_along(route['coords'])],
                           route['distance_miles'], range_miles=RANGE_MILES)
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
        'route': {'type': 'LineString', 'coordinates': [[round(x, 5), round(y, 5)] for x, y in line]},
    }
    cache.set(key, result)
    return result, 1 + start['external'] + finish['external']


def plan_for(request):
    """(result, None) or (None, (status, code, detail)) for the request's start/finish."""
    start, finish = (request.GET.get(k, '').strip() for k in ('start', 'finish'))
    if not start or not finish:
        return None, (400, 'missing_parameter', 'Both "start" and "finish" are required.')
    try:
        result, calls = plan(start, finish)
    except ValueError as e:
        return None, (400, 'unknown_location', f'Could not resolve to a US location: {e}')
    except Unreachable as e:
        a, b = e.gap_start_mile, e.gap_end_mile
        return None, (422, 'unreachable', f'No fuel station between mile {a:.1f} and mile {b:.1f} '
                                          f'({b - a:.1f} mi gap, range is {RANGE_MILES} mi).')
    except geo.RoutingError as e:
        return None, (502, 'routing_provider_error', str(e))
    query = urlencode({'start': start, 'finish': finish})
    result['start']['query'], result['finish']['query'] = start, finish  # cache hit may have other spelling
    result['map_url'] = request.build_absolute_uri(f"{reverse('route_map')}?{query}")
    result['external_api_calls'] = calls
    return result, None


@csrf_exempt  # read-only JSON; lets a POST get 405 instead of a CSRF 403
@require_GET
def route_api(request):
    result, err = plan_for(request)
    if err:
        return JsonResponse({'error': err[1], 'detail': err[2]}, status=err[0])
    return JsonResponse(result)


@require_GET
def route_map(request):
    if not request.GET.get('start') and not request.GET.get('finish'):
        return render(request, 'routing/map.html', {})  # empty demo form
    result, err = plan_for(request)
    return render(request, 'routing/map.html', {'plan': result, 'error': err and err[2]},
                  status=err[0] if err else 200)


@require_GET
def openapi(request):
    path = settings.BASE_DIR / 'openapi.yaml'
    if not path.exists():
        raise Http404('openapi.yaml not found')
    return FileResponse(path.open('rb'), content_type='application/yaml')

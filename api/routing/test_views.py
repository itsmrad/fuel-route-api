from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from routing import geo
from routing.models import Station

COORDS = [[round(-96.8 + i * 0.054, 6), 32.78] for i in range(201)]  # ~630 mi due east of Dallas


def polyline6(coords):
    out, prev = [], [0, 0]
    for lon, lat in coords:
        for k, v in enumerate((round(lat * 1e6), round(lon * 1e6))):
            d, prev[k] = v - prev[k], v
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 32:
                out.append(chr((32 | d & 31) + 63))
                d >>= 5
            out.append(chr(d + 63))
    return ''.join(out)


OSRM_OK = {'code': 'Ok', 'routes': [{'geometry': polyline6(COORDS), 'distance': 630 * 1609.344, 'duration': 9 * 3600}]}
PLACES = {('TX', 'dallas'): (32.78, -96.8), ('MS', 'east'): (32.78, -86.0)}
URL = '/api/route/?start=Dallas, TX&finish=East, MS'
SHAPE = '_p~iF~ps|U_ulLnnqC_mqNvxq`@'  # Google's polyline example, read at 1e-6
VALHALLA_OK = {'trip': {'legs': [{'shape': SHAPE}], 'summary': {'length': 300.0, 'time': 5 * 3600}}}
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def fake_get(osrm):
    """osrm: one reply for every OSRM host, or a list with one per host."""
    def get(url, **kw):
        host = next((h for h in geo.OSRM if url.startswith(h)), None)
        reply = osrm[geo.OSRM.index(host)] if host and isinstance(osrm, list) else osrm
        if host and isinstance(reply, Exception):
            raise reply
        r = MagicMock()
        r.json.return_value = reply if host else []  # Nominatim: nothing found
        return r
    return get


@override_settings(CACHES=LOCMEM)
@patch('routing.geo.time.sleep')  # Nominatim throttle
@patch('routing.geo.places', return_value=PLACES)
class RouteApiTests(TestCase):
    def setUp(self):
        cache.clear()
        geo.grid.cache_clear()
        for i, (lon, price) in enumerate([(-95.0, '3.0'), (-91.0, '3.5')]):
            Station.objects.create(opis_id=i, name=f'S{i}', address=f'I-20 EXIT {i}', city='C', state='TX',
                                   price=Decimal(price), lat=32.8, lon=lon)

    def tearDown(self):
        geo.grid.cache_clear()

    def get(self, url=URL, osrm=OSRM_OK):
        with patch('routing.geo.http.get', side_effect=fake_get(osrm)) as get:
            return self.client.get(url), get

    def truck(self, valhalla, url=URL + '&vehicle=truck', osrm=OSRM_OK):
        post = MagicMock(side_effect=valhalla) if isinstance(valhalla, Exception) else MagicMock()
        post.return_value.json.return_value = valhalla
        with patch('routing.geo.http.post', post):
            r, get = self.get(url, osrm)
        return r, post.call_count + get.call_count

    def test_truck_uses_valhalla(self, *_):
        r, calls = self.truck(VALHALLA_OK)
        body = r.json()
        self.assertEqual((r.status_code, calls, body['external_api_calls']), (200, 1, 1))
        self.assertEqual(body['routing'], {'provider': 'valhalla', 'profile': 'truck', 'fallback': False})
        self.assertEqual((body['distance_miles'], body['duration_hours']), (300.0, 5.0))
        self.assertEqual(body['route']['coordinates'], [[-12.02, 3.85], [-12.095, 4.07], [-12.6453, 4.3252]])
        self.assertTrue(body['map_url'].endswith('&vehicle=truck'))

    def test_truck_falls_back_to_osrm(self, *_):
        for valhalla in (requests.ConnectionError('boom'), {'error_code': 154, 'error': 'too far'}):
            cache.clear()
            r, calls = self.truck(valhalla)
            self.assertEqual((r.status_code, calls, r.json()['external_api_calls']), (200, 2, 2))
            self.assertEqual(r.json()['routing'], {'provider': 'osrm', 'profile': 'car', 'fallback': True})
            self.assertEqual(r.json()['distance_miles'], 630.0)

    def test_truck_over_public_cap_skips_valhalla(self, *_):
        r, calls = self.truck(AssertionError('not called'), '/api/route/?start=Dallas, TX&finish=47.6,-122.3&vehicle=truck')
        self.assertEqual((calls, r.json()['external_api_calls'], r.json()['routing']['fallback']), (1, 1, True))

    def test_truck_no_path(self, *_):
        r, _ = self.truck({'error_code': 442, 'error': 'No path could be found for input'})
        self.assertEqual((r.status_code, r.json()['error']), (422, 'no_route'))

    def test_vehicle_in_cache_key(self, *_):
        self.assertEqual(self.get()[1].call_count, 1)
        self.assertEqual(self.truck(VALHALLA_OK)[1], 1)  # car route cached, truck still routes
        self.assertEqual(self.truck(VALHALLA_OK)[1], 0)
        r, get = self.get(URL + '&vehicle=car')
        self.assertEqual((get.call_count, r.json()['distance_miles']), (0, 630.0))
        r, _ = self.get(URL + '&vehicle=bike')
        self.assertEqual((r.status_code, r.json()['error']), (400, 'invalid_parameter'))

    def test_happy_path_then_cache_hit(self, *_):
        r, get = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(get.call_count, 1)  # one OSRM call, both cities resolved locally
        body = r.json()
        self.assertEqual(set(body), {'start', 'finish', 'distance_miles', 'duration_hours', 'fuel_stops',
                                     'total_gallons_purchased', 'total_fuel_cost', 'cost_of_fuel_consumed',
                                     'stop_penalty', 'route', 'map_url', 'external_api_calls', 'routing'})
        self.assertEqual(body['routing'], {'provider': 'osrm', 'profile': 'car', 'fallback': False})
        self.assertEqual(body['start'], {'query': 'Dallas, TX', 'lat': 32.78, 'lon': -96.8})
        self.assertEqual((body['distance_miles'], body['duration_hours'], body['external_api_calls']), (630.0, 9.0, 1))
        self.assertEqual([s['name'] for s in body['fuel_stops']], ['S0', 'S1'])
        self.assertEqual(set(body['fuel_stops'][0]),
                         {'mile', 'name', 'address', 'city', 'state', 'lat', 'lon', 'price', 'gallons', 'cost'})
        self.assertAlmostEqual(body['total_fuel_cost'], sum(s['cost'] for s in body['fuel_stops']), delta=0.01)
        self.assertEqual(body['route']['type'], 'LineString')
        self.assertEqual(body['route']['coordinates'][-1], COORDS[-1])
        self.assertEqual(body['map_url'], 'http://testserver/api/route/map/?start=Dallas%2C+TX&finish=East%2C+MS&stop_penalty=15.0&vehicle=car')

        r, get = self.get('/api/route/?start= dallas , tx &finish=EAST,MS')
        self.assertEqual(get.call_count, 0)
        self.assertEqual(r.json()['external_api_calls'], 0)
        self.assertEqual(r.json()['start']['query'], 'dallas , tx')
        self.assertEqual(r.json()['fuel_stops'], body['fuel_stops'])

    def test_missing_param(self, *_):
        r, _ = self.get('/api/route/?start=Dallas, TX')
        self.assertEqual((r.status_code, r.json()['error']), (400, 'missing_parameter'))

    def test_stop_penalty(self, *_):
        r, _ = self.get()
        self.assertEqual((r.json()['stop_penalty'], len(r.json()['fuel_stops'])), (15.0, 2))
        r, get = self.get(URL + '&stop_penalty=0')
        self.assertEqual((get.call_count, r.json()['external_api_calls']), (0, 0))  # route cached, optimizer re-run
        self.assertEqual(r.json()['stop_penalty'], 0.0)
        r, get = self.get(URL + '&stop_penalty=1000')  # one pricier stop beats two
        self.assertEqual(get.call_count, 0)
        self.assertEqual([s['name'] for s in r.json()['fuel_stops']], ['S1'])
        for bad in ('-1', 'abc', 'nan', 'inf'):
            r, _ = self.get(f'{URL}&stop_penalty={bad}')
            self.assertEqual((r.status_code, r.json()['error']), (400, 'invalid_parameter'), bad)

    def test_unknown_location(self, *_):
        r, _ = self.get('/api/route/?start=Dallas, TX&finish=Nowhere, ZZ')
        self.assertEqual((r.status_code, r.json()['error']), (400, 'unknown_location'))

    def test_unreachable(self, *_):
        Station.objects.all().delete()
        r, _ = self.get()
        self.assertEqual((r.status_code, r.json()['error']), (422, 'unreachable'))
        self.assertIn('between mile 0.0 and mile 630.0', r.json()['detail'])

    def test_no_route(self, *_):
        r, _ = self.get(osrm={'code': 'NoRoute', 'message': 'Impossible route between points'})
        self.assertEqual((r.status_code, r.json()['error']), (422, 'no_route'))

    def test_same_start_and_finish(self, *_):
        r, get = self.get('/api/route/?start=Dallas, TX&finish=32.78,-96.8')
        body = r.json()
        self.assertEqual((r.status_code, get.call_count, body['external_api_calls']), (200, 0, 0))
        self.assertEqual((body['distance_miles'], body['fuel_stops'], body['total_fuel_cost']), (0.0, [], 0.0))

    def test_routing_down(self, *_):
        r, get = self.get(osrm=requests.ConnectionError('boom'))
        self.assertEqual((r.status_code, r.json()['error'], get.call_count), (502, 'routing_provider_error', 2))
        r, calls = self.truck(requests.ReadTimeout('slow'), osrm=requests.ReadTimeout('slow'))
        self.assertEqual((r.status_code, calls), (502, 3))  # worst case: Valhalla + both OSRM hosts

    def test_second_osrm_host_on_failure(self, *_):
        for primary in (requests.ReadTimeout('slow'), {'code': 'TooBig', 'message': 'busy'}):
            cache.clear()
            r, get = self.get(osrm=[primary, OSRM_OK])
            body = r.json()
            self.assertEqual((r.status_code, get.call_count, body['external_api_calls']), (200, 2, 2))
            self.assertEqual([c.args[0].startswith(h) for c, h in zip(get.call_args_list, geo.OSRM)], [True, True])
            self.assertEqual(body['routing'], {'provider': 'osrm', 'profile': 'car', 'fallback': True})
            self.assertEqual(body['distance_miles'], 630.0)
        r, calls = self.truck(requests.ConnectionError('boom'), osrm=[requests.ReadTimeout('slow'), OSRM_OK])
        self.assertEqual((r.status_code, calls, r.json()['external_api_calls']), (200, 3, 3))

    def test_no_route_skips_second_host(self, *_):
        r, get = self.get(osrm=[{'code': 'NoRoute', 'message': 'Impossible route'}, AssertionError('not called')])
        self.assertEqual((r.status_code, get.call_count), (422, 1))

    def test_get_only(self, *_):
        r = Client(enforce_csrf_checks=True).post(URL)
        self.assertEqual((r.status_code, r.json()['error']), (405, 'method_not_allowed'))

    def test_api_404_is_json(self, *_):
        r = self.client.get('/api/nope/')
        self.assertEqual((r.status_code, r.json()['error']), (404, 'not_found'))

    def test_openapi_served(self, *_):
        r = self.client.get('/api/openapi.yaml')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(b''.join(r.streaming_content).startswith(b'openapi:'))

    def test_map_page(self, *_):
        r, get = self.get(URL.replace('/route/', '/route/map/'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'leaflet')
        self.assertContains(r, '"S1"')
        self.assertEqual(self.client.get('/api/route/map/').status_code, 200)  # empty demo form
        r = self.client.get('/api/route/map/?start=Dallas, TX')
        self.assertContains(r, 'Both start and finish are required.', status_code=400)
        r, _ = self.get('/api/route/map/?start=Dallas, TX&finish=Nowhere, ZZ')
        self.assertEqual((r.status_code, r.json()['error']), (400, 'unknown_location'))

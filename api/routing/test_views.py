from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import Client, TestCase

from routing import geo
from routing.models import Station

COORDS = [[-96.8 + i * 0.054, 32.78] for i in range(201)]  # ~630 mi due east of Dallas
OSRM_OK = {'code': 'Ok', 'routes': [{'geometry': {'coordinates': COORDS}, 'distance': 630 * 1609.344, 'duration': 9 * 3600}]}
PLACES = {('TX', 'dallas'): (32.78, -96.8), ('MS', 'east'): (32.78, -86.0)}
URL = '/api/route/?start=Dallas, TX&finish=East, MS'


def fake_get(osrm):
    def get(url, **kw):
        if isinstance(osrm, Exception) and url.startswith(geo.OSRM):
            raise osrm
        r = MagicMock()
        r.json.return_value = osrm if url.startswith(geo.OSRM) else []  # Nominatim: nothing found
        return r
    return get


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
        with patch('routing.geo.requests.get', side_effect=fake_get(osrm)) as get:
            return self.client.get(url), get

    def test_happy_path_then_cache_hit(self, _):
        r, get = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(get.call_count, 1)  # one OSRM call, both cities resolved locally
        body = r.json()
        self.assertEqual(set(body), {'start', 'finish', 'distance_miles', 'duration_hours', 'fuel_stops',
                                     'total_gallons_purchased', 'total_fuel_cost', 'cost_of_fuel_consumed',
                                     'route', 'map_url', 'external_api_calls'})
        self.assertEqual(body['start'], {'query': 'Dallas, TX', 'lat': 32.78, 'lon': -96.8})
        self.assertEqual((body['distance_miles'], body['duration_hours'], body['external_api_calls']), (630.0, 9.0, 1))
        self.assertEqual([s['name'] for s in body['fuel_stops']], ['S0', 'S1'])
        self.assertEqual(set(body['fuel_stops'][0]),
                         {'mile', 'name', 'address', 'city', 'state', 'lat', 'lon', 'price', 'gallons', 'cost'})
        self.assertAlmostEqual(body['total_fuel_cost'], sum(s['cost'] for s in body['fuel_stops']), delta=0.01)
        self.assertEqual(body['route']['type'], 'LineString')
        self.assertEqual(body['route']['coordinates'][-1], COORDS[-1])
        self.assertEqual(body['map_url'], 'http://testserver/api/route/map/?start=Dallas%2C+TX&finish=East%2C+MS')

        r, get = self.get('/api/route/?start=dallas,  tx&finish=EAST, MS')
        self.assertEqual(get.call_count, 0)
        self.assertEqual(r.json()['external_api_calls'], 0)
        self.assertEqual(r.json()['fuel_stops'], body['fuel_stops'])

    def test_missing_param(self, _):
        r, _ = self.get('/api/route/?start=Dallas, TX')
        self.assertEqual((r.status_code, r.json()['error']), (400, 'missing_parameter'))

    def test_unknown_location(self, _):
        r, _ = self.get('/api/route/?start=Dallas, TX&finish=Nowhere, ZZ')
        self.assertEqual((r.status_code, r.json()['error']), (400, 'unknown_location'))

    def test_unreachable(self, _):
        Station.objects.all().delete()
        r, _ = self.get()
        self.assertEqual((r.status_code, r.json()['error']), (422, 'unreachable'))
        self.assertIn('between mile 0.0 and mile 630.0', r.json()['detail'])

    def test_routing_down(self, _):
        r, _ = self.get(osrm=requests.ConnectionError('boom'))
        self.assertEqual((r.status_code, r.json()['error']), (502, 'routing_provider_error'))

    def test_get_only(self, _):
        self.assertEqual(Client(enforce_csrf_checks=True).post(URL).status_code, 405)

    def test_map_page(self, _):
        r, get = self.get(URL.replace('/route/', '/route/map/'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'leaflet')
        self.assertContains(r, '"S1"')
        self.assertEqual(self.client.get('/api/route/map/').status_code, 200)  # empty demo form

import threading
from decimal import Decimal
from unittest.mock import patch

import requests

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from routing import geo
from routing.models import Station
from routing.test_views import LOCMEM


@override_settings(CACHES=LOCMEM)
@patch('routing.geo.time.sleep')
@patch('routing.geo.http.get', side_effect=AssertionError('no network in tests'))
@patch('routing.geo.places', return_value={('TX', 'dallas'): (32.79, -96.77), ('MO', 'stlouis'): (38.64, -90.24)})
class ResolveTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_city_state_is_local(self, *_):
        self.assertEqual(geo.resolve(' dallas , tx '), {'lat': 32.79, 'lon': -96.77, 'external': False})
        self.assertEqual(geo.resolve('Saint Louis, MO')['lat'], 38.64)

    def test_lat_lon(self, *_):
        r = geo.resolve('40.7128, -74.006')
        self.assertEqual((r['lat'], r['lon'], r['external']), (40.7128, -74.006, False))
        self.assertEqual(geo.resolve('21.3,-157.85')['lat'], 21.3)  # Honolulu

    def test_rejects_outside_usa(self, *_):
        for q in ['51.5,-0.12', '49.28,-123.12', '91,0', '']:  # London, Vancouver
            with self.assertRaises(ValueError, msg=q):
                geo.resolve(q)

    def test_nominatim_cached_and_throttled(self, _, get, sleep):
        get.side_effect = None
        get.return_value.json.return_value = [{'lat': '35.0', 'lon': '-90.0'}]
        self.assertTrue(geo.resolve('Somewhere TN')['external'])
        r = geo.resolve('  somewhere   tn ')
        self.assertEqual((r['lat'], r['external'], get.call_count), (35.0, False, 1))
        geo.resolve('Elsewhere TN')
        self.assertGreater(sleep.call_args[0][0], 0.9)  # second live call waits out the 1 s gap

    def test_nominatim_fallback_rejects_non_us_hit(self, _, get, _sleep):
        get.side_effect = None
        get.return_value.json.return_value = [{'lat': '51.5', 'lon': '-0.12'}]
        with self.assertRaises(ValueError):
            geo.resolve('London')
        get.return_value.json.return_value = []
        with self.assertRaises(ValueError):
            geo.resolve('Nowhere, ZZ')


class StationsAlongTests(TestCase):
    def setUp(self):
        geo.grid.cache_clear()
        for i, (lat, lon) in enumerate([(33.05, -96.5), (33.0, -96.9), (33.5, -96.5)]):
            Station.objects.create(opis_id=i, name=f'S{i}', address='', city='', state='TX',
                                   price=Decimal('3.1'), lat=lat, lon=lon)

    def tearDown(self):
        geo.grid.cache_clear()

    def test_corridor_sorted_by_mile(self):
        coords = [[-97 + i * 0.005, 33.0] for i in range(201)]  # ~58 mi due east
        got = geo.stations_along(coords)
        self.assertEqual([s.name for _, s in got], ['S1', 'S0'])  # S2 is ~34 mi off the route
        self.assertAlmostEqual(got[0][0], 5.8, delta=1)
        self.assertAlmostEqual(got[1][0], 29.0, delta=1)


class DeadlineTests(SimpleTestCase):
    @patch('routing.geo.DEADLINE', 0.05)
    def test_slow_call_gives_up(self):
        with self.assertRaises(requests.Timeout):
            geo.call(lambda url, **kw: threading.Event().wait(1), 'https://slow')


class Polyline6Tests(SimpleTestCase):
    def test_decode(self):  # Google's precision-5 example, so every coordinate reads 10x smaller at 1e-6
        self.assertEqual(geo.polyline6('_p~iF~ps|U_ulLnnqC_mqNvxq`@'), [[-12.02, 3.85], [-12.095, 4.07], [-12.6453, 4.3252]])
        self.assertEqual(geo.polyline6(''), [])

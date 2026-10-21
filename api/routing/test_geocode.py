import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from routing.management.commands.geocode_stations import accept
from routing.models import Station

DALLAS = (32.79, -96.77)


class AcceptTests(SimpleTestCase):
    def test_guard(self):
        hit = {'result_type': 'street', 'rank': {'confidence': 0.9}, 'lat': 32.70, 'lon': -96.70}  # ~7 mi off
        self.assertEqual(accept(hit, DALLAS), (32.70, -96.70, 0.9))
        self.assertIsNone(accept({**hit, 'lat': 33.3}, DALLAS))  # ~35 mi off: a same-named place elsewhere
        self.assertIsNone(accept({**hit, 'result_type': 'city'}, DALLAS))  # no better than the centroid
        self.assertIsNone(accept({**hit, 'rank': {'confidence': 0.2}}, DALLAS))
        self.assertIsNone(accept(None, DALLAS))


@patch('routing.management.commands.load_stations.build_index', return_value={('TX', 'dallas'): DALLAS})
class CoordsOverrideTests(TestCase):
    def load(self, csv_text):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'station_coords.csv'
            path.write_text(csv_text)
            with patch('routing.management.commands.load_stations.COORDS', path):
                call_command('load_stations', stdout=StringIO())

    def test_csv_overrides_centroid(self, _):
        self.load('opis_id,lat,lon,source,confidence\n52221,32.68,-96.86,geoapify,0.9\n6227,1,1,centroid,\n')
        self.assertEqual((Station.objects.get(opis_id=52221).lat, Station.objects.get(opis_id=52221).lon),
                         (32.68, -96.86))
        self.assertEqual(Station.objects.get(opis_id=6227).lat, DALLAS[0])  # rejected hit keeps the centroid
        self.assertEqual(Station.objects.get(opis_id=52361).lat, DALLAS[0])  # not in the CSV

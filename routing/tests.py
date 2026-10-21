from django.test import SimpleTestCase

from routing.management.commands.load_stations import aliases, normalize


class NormalizeTests(SimpleTestCase):
    def test_csv_and_gazetteer_names_meet(self):  # CSV side is looked up unstripped first
        for csv_city, gaz_name in [
            ('Abbeville', 'Abbeville city'),
            ('St. Louis', 'St. Louis city'),
            ('Saint Joseph', 'St. Joseph city'),
            ('Mc Calla', 'McCalla CDP'),
            ('Canon City', 'Cañon City city'),
            ('Indianapolis', 'Indianapolis city (balance)'),
            ("O'Fallon", 'O\'Fallon city'),
        ]:
            self.assertEqual(normalize(csv_city, False), normalize(gaz_name), csv_city)

    def test_consolidated_city_aliases(self):
        self.assertIn('athens', aliases('Athens-Clarke County unified government (balance)'))
        self.assertIn('augusta', aliases('Augusta-Richmond County consolidated government (balance)'))
        self.assertIn('boise', aliases('Boise City city'))
        self.assertEqual(normalize('Boise City', False), normalize('Boise City city'))  # Boise City, OK

import csv
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.geo import US_STATES, build_index, normalize
from routing.models import Station

COORDS = settings.BASE_DIR / 'data' / 'station_coords.csv'  # written once by geocode_stations, committed


def centroid_stations():
    """(rows read, unique US stations, unsaved Stations at their Census city centroid, unmatched 'City, ST')."""
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
        # unstripped, so 'Junction City' never falls to a place named 'Junction'
        ll = index.get((state, normalize(city, False)))
        if ll is None:
            unmatched.append(f'{city}, {state}')
            continue
        stations.append(Station(
            opis_id=sid, name=r['Truckstop Name'].strip(), address=r['Address'].strip(),
            city=city, state=state, price=price, lat=ll[0], lon=ll[1],
        ))
    return len(rows), len(best), stations, unmatched


class Command(BaseCommand):
    help = 'Load fuel-prices.csv into Station: geocoded address from station_coords.csv, else Census city centroid.'

    def handle(self, *args, **opts):
        n_rows, n_best, stations, unmatched = centroid_stations()
        if not stations:
            raise CommandError('No stations matched; refusing to wipe the Station table.')

        precise = 0
        if COORDS.exists():
            with open(COORDS, newline='') as f:
                coords = {int(c['opis_id']): c for c in csv.DictReader(f) if c['source'] != 'centroid'}
            for s in stations:
                if c := coords.get(s.opis_id):
                    s.lat, s.lon, precise = float(c['lat']), float(c['lon']), precise + 1

        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create(stations)

        self.stdout.write(
            f'rows read: {n_rows}\nunique US stations: {n_best}\n'
            f'matched: {len(stations)} ({len(stations) / n_best:.1%})\nunmatched: {len(unmatched)}\n'
            f'address-geocoded: {precise} ({precise / len(stations):.1%}), rest at city centroid'
        )
        if unmatched:
            self.stdout.write('first unmatched: ' + '; '.join(sorted(set(unmatched))[:20]))

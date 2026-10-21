import csv
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.geo import US_STATES, build_index, normalize
from routing.models import Station


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
            # unstripped, so 'Junction City' never falls to a place named 'Junction'
            ll = index.get((state, normalize(city, False)))
            if ll is None:
                unmatched.append(f'{city}, {state}')
                continue
            stations.append(Station(
                opis_id=sid, name=r['Truckstop Name'].strip(), address=r['Address'].strip(),
                city=city, state=state, price=price, lat=ll[0], lon=ll[1],
            ))

        if not stations:
            raise CommandError('No stations matched; refusing to wipe the Station table.')
        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create(stations)

        self.stdout.write(
            f'rows read: {len(rows)}\nunique US stations: {len(best)}\n'
            f'matched: {len(stations)} ({len(stations) / len(best):.1%})\nunmatched: {len(unmatched)}'
        )
        if unmatched:
            self.stdout.write('first unmatched: ' + '; '.join(sorted(set(unmatched))[:20]))

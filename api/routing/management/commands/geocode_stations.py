import csv
import os
import re
import time
from collections import Counter

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from routing.geo import haversine
from routing.management.commands.load_stations import COORDS, centroid_stations

BATCH = 'https://api.geoapify.com/v1/batch'
INTERSTATE = re.compile(r'\bI-?\s?\d')
# ponytail: thresholds eyeballed on a sample; a street-level hit in the right city beats the centroid,
# anything coarser (city/postcode/county) or far from the centroid (wrong same-named place) does not.
GOOD_TYPES = {'building', 'amenity', 'street'}
MIN_CONFIDENCE = 0.5
MAX_MILES = 25


def accept(hit, centroid):
    """(lat, lon, confidence) when a Geoapify hit is precise and near the city centroid, else None."""
    if not hit or hit.get('result_type') not in GOOD_TYPES:
        return None
    conf = hit.get('rank', {}).get('confidence', 0)
    if conf < MIN_CONFIDENCE or haversine(*centroid, hit['lat'], hit['lon']) > MAX_MILES:
        return None
    return hit['lat'], hit['lon'], conf


def api_key():
    if key := os.environ.get('GEOAPIFY_API_KEY'):
        return key
    env = settings.BASE_DIR / '.env'
    for line in env.read_text().splitlines() if env.exists() else ():
        if line.startswith('GEOAPIFY_API_KEY='):
            return line.split('=', 1)[1].strip().strip('"\'')
    raise CommandError('GEOAPIFY_API_KEY not set (env or api/.env)')


class Command(BaseCommand):
    help = ('One-time: geocode station addresses with the Geoapify batch API into data/station_coords.csv. '
            'Resumable; stations already in the CSV are skipped.')

    def add_arguments(self, parser):
        # ponytail: free tier is 3,000 credits/day at 0.5/address + ~1 per job call; 5,000 stays >10% under
        parser.add_argument('--limit', type=int, default=5000, help='max unique addresses to send')

    def handle(self, *args, limit, **opts):
        key = api_key()
        _, _, stations, _ = centroid_stations()
        done = {}
        if COORDS.exists():
            with open(COORDS, newline='') as f:
                done = {int(r['opis_id']): r for r in csv.DictReader(f)}

        groups = {}  # many OPIS rows share one address: geocode each once
        for s in stations:
            if s.opis_id not in done:
                k = (' '.join(s.address.upper().split()), s.city.upper(), s.state)
                groups.setdefault(k, []).append(s)
        per_state = Counter(s.state for s in stations)
        todo = sorted(groups, key=lambda k: (not INTERSTATE.search(k[0]), -per_state[k[2]], k))
        self.stdout.write(f'unique addresses to geocode: {len(todo)}, sending {min(limit, len(todo))}')
        todo = todo[:limit]

        def call(method, **kw):
            try:
                r = requests.request(method, BATCH, params={'apiKey': key, **kw.pop('params', {})}, timeout=60, **kw)
                r.raise_for_status()
                return r.status_code, r.json()
            except requests.RequestException as e:  # never let the key reach the console
                raise CommandError(str(e).replace(key, '***')) from None

        jobs = []
        for i in range(0, len(todo), 1000):
            chunk = todo[i:i + 1000]
            body = {'api': '/v1/geocode/search',
                    'params': {'filter': 'countrycode:us', 'limit': 1, 'format': 'json', 'lang': 'en'},
                    'inputs': [{'id': str(i + j), 'params': {'street': a, 'city': c, 'state': st, 'country': 'us'}}
                               for j, (a, c, st) in enumerate(chunk)]}
            jobs.append(call('POST', json=body)[1]['id'])
            self.stdout.write(f'submitted job {len(jobs)} ({len(chunk)} addresses)')

        polls, accepted = 0, 0
        for job in jobs:
            while True:
                time.sleep(300)  # each poll costs a credit; low-priority jobs take a while
                status, data = call('GET', params={'id': job})
                polls += 1
                if status == 200 and isinstance(data, list):
                    break
            for item in data:
                k = todo[int(item['id'])]
                hits = (item.get('result') or {}).get('results') or [None]
                for s in groups[k]:
                    if got := accept(hits[0], (s.lat, s.lon)):
                        accepted += 1
                        done[s.opis_id] = {'opis_id': s.opis_id, 'lat': round(got[0], 6), 'lon': round(got[1], 6),
                                           'source': 'geoapify', 'confidence': round(got[2], 3)}
                    else:
                        done[s.opis_id] = {'opis_id': s.opis_id, 'lat': s.lat, 'lon': s.lon,
                                           'source': 'centroid', 'confidence': ''}
            self.stdout.write(f'job {job[:8]} done')

        with open(COORDS, 'w', newline='') as f:
            w = csv.DictWriter(f, ['opis_id', 'lat', 'lon', 'source', 'confidence'])
            w.writeheader()
            w.writerows(done[k] for k in sorted(done))
        self.stdout.write(f'accepted {accepted} stations; {len(jobs)} jobs, {polls} polls; '
                          f'~{len(todo) / 2 + len(jobs) + polls:.0f} credits')

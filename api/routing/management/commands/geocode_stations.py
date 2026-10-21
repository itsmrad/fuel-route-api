import csv
import json
import os
import re
import time
from collections import Counter

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from routing.geo import haversine
from routing.management.commands.load_stations import COORDS, centroid_stations

# Free-text batch endpoint: 0.5 credit/address. The structured /v1/batch variant sat 'pending' for 40+ min.
BATCH = 'https://api.geoapify.com/v1/batch/geocode/search'
INTERSTATE = re.compile(r'\bI-?\s?\d')
# ponytail: thresholds eyeballed on the first run's answers. A building/street/amenity hit sharing a number with
# the address (house number, route or exit: 'US-259' -> 'US Highway 259', not 'Trail Exit') beats the centroid;
# city/postcode-level hits and anything > 25 mi from the centroid (a same-named place elsewhere) do not.
# Most 'I-xx, EXIT nn' addresses only resolve to the city and keep the centroid; an exit lookup table is the upgrade.
GOOD_TYPES = {'building', 'amenity', 'street'}
MIN_CONFIDENCE = 0.5
MAX_MILES = 25


def accept(hit, centroid, address):
    """(lat, lon, confidence) when a Geoapify hit is precise and near the city centroid, else None."""
    if not hit or hit.get('result_type') not in GOOD_TYPES or 'lat' not in hit:
        return None
    conf = hit.get('rank', {}).get('confidence', 0)
    if conf < MIN_CONFIDENCE or haversine(*centroid, hit['lat'], hit['lon']) > MAX_MILES:
        return None
    if not set(re.findall(r'\d+', address)) & set(re.findall(r'\d+', hit.get('address_line1', ''))):
        return None  # 'I-35, EXIT 140' -> 'Interchange 140' or 'I 35' passes; 'Trail Exit', 'Exit Realty' don't
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
        # ponytail: free tier is 3,000 credits/day at 0.5/address + 1 per job call/poll; 5,000 stays >10% under
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
                groups.setdefault(f"{' '.join(s.address.split())}, {s.city}, {s.state}, United States", []).append(s)
        per_state = Counter(s.state for s in stations)
        todo = sorted(groups, key=lambda q: (not INTERSTATE.search(q), -per_state[groups[q][0].state], q))
        self.stdout.write(f'unique addresses to geocode: {len(todo)}, sending {min(limit, len(todo))}')
        todo = todo[:limit]

        def call(method, **kw):
            try:
                r = requests.request(method, BATCH, timeout=60, **kw)
                r.raise_for_status()
                return r.status_code, r.json()
            except requests.RequestException as e:  # never let the key reach the console
                raise CommandError(str(e).replace(key, '***')) from None

        raw = settings.BASE_DIR / '.cache' / 'geoapify_raw.json'  # paid-for answers; re-filtering costs nothing
        hits = json.loads(raw.read_text()) if raw.exists() else {}
        send = [q for q in todo if q not in hits]
        self.stdout.write(f'{len(todo) - len(send)} answers cached, {len(send)} to send')
        params = {'apiKey': key, 'filter': 'countrycode:us', 'lang': 'en'}
        chunks = [send[i:i + 1000] for i in range(0, len(send), 1000)]
        jobs = [call('POST', params=params, json=chunk)[1]['id'] for chunk in chunks]
        self.stdout.write(f'submitted {len(jobs)} jobs')

        polls = 0
        for job, chunk in zip(jobs, chunks):
            while True:
                time.sleep(60)  # each poll costs a credit
                status, data = call('GET', params={'apiKey': key, 'id': job, 'format': 'json'})
                polls += 1
                if status == 200 and isinstance(data, list):
                    break
            if len(data) != len(chunk):
                raise CommandError(f'job returned {len(data)} results for {len(chunk)} addresses')
            hits.update(zip(chunk, data))  # results come back in input order
            raw.parent.mkdir(exist_ok=True)
            raw.write_text(json.dumps(hits))
            self.stdout.write(f'{len(hits)} answers saved')

        accepted = 0
        for q in todo:
            for s in groups[q]:
                if got := accept(hits.get(q), (s.lat, s.lon), s.address):
                    accepted += 1
                    done[s.opis_id] = {'opis_id': s.opis_id, 'lat': round(got[0], 6), 'lon': round(got[1], 6),
                                       'source': 'geoapify', 'confidence': round(got[2], 2)}
                else:  # tried and rejected: recorded so a resumed run doesn't pay for it again
                    done[s.opis_id] = {'opis_id': s.opis_id, 'lat': round(s.lat, 6), 'lon': round(s.lon, 6),
                                       'source': 'centroid', 'confidence': ''}

        with open(COORDS, 'w', newline='') as f:
            w = csv.DictWriter(f, ['opis_id', 'lat', 'lon', 'source', 'confidence'])
            w.writeheader()
            w.writerows(done[k] for k in sorted(done))
        self.stdout.write(f'accepted {accepted} stations; {len(jobs)} jobs, {polls} polls, '
                          f'~{len(send) / 2 + len(jobs) + polls:.0f} credits')

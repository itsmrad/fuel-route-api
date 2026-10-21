import datetime
import gzip
import json
import math
import platform
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.http import JsonResponse

from routing import geo, views
from routing.optimizer import Unreachable, plan_fuel_stops

PAIRS = [
    ('Austin, TX', 'Dallas, TX'), ('Boston, MA', 'Washington, DC'), ('Phoenix, AZ', 'Salt Lake City, UT'),
    ('Houston, TX', 'Atlanta, GA'), ('Minneapolis, MN', 'Memphis, TN'), ('Jacksonville, FL', 'Indianapolis, IN'),
    ('Dallas, TX', 'Chicago, IL'), ('Las Vegas, NV', 'Kansas City, MO'), ('Denver, CO', 'Atlanta, GA'),
    ('Chicago, IL', 'Houston, TX'), ('New York, NY', 'Los Angeles, CA'), ('Miami, FL', 'Seattle, WA'),
]
CACHED_REPEATS, PENALTIES, COLD_GAP = 20, (0, 15, 40), 1.5  # public OSRM etiquette: ~1 req/s
TANK, MPG, RESERVE = 500, 10, 100
DOC = settings.BASE_DIR.parent / 'docs' / 'content' / 'docs' / 'benchmarks.mdx'


def naive(corridor, total, reserve=RESERVE):
    """(net $, stops) for a driver who, at each corridor station, fills to full when the finish is out of reach and
    the next station would be reached with under `reserve` miles left. Fuel left at the finish is credited back
    at the last fill price, so a full tank on arrival isn't counted as spend."""
    pts = sorted((float(m), float(p)) for m, p, _ in corridor if 0 <= m <= total)
    fuel, pos, cost, stops, last = TANK, 0.0, 0.0, 0, 0.0
    for i, (m, p) in enumerate(pts):
        if m - pos > fuel:
            raise Unreachable(pos, m)
        fuel, pos = fuel - (m - pos), m
        nxt = pts[i + 1][0] if i + 1 < len(pts) else total
        if fuel < total - m and fuel - (nxt - m) < reserve and fuel < TANK:
            cost, fuel, stops, last = cost + (TANK - fuel) / MPG * p, TANK, stops + 1, p
    if total - pos > fuel:
        raise Unreachable(pos, total)
    fuel -= total - pos
    return cost - fuel / MPG * last, stops


def pct(xs, q):
    xs = sorted(xs)
    return xs[max(0, math.ceil(q * len(xs)) - 1)]


def ms(x):
    x *= 1000
    return f'{x:,.0f}' if x >= 10 else f'{x:.1f}' if x >= 0.1 else f'{x:.2f}'


def get(base, start, finish, **params):
    url = f"{base}/api/route/?{urllib.parse.urlencode({'start': start, 'finish': finish, **params})}"
    t = time.perf_counter()
    with urllib.request.urlopen(url, timeout=60) as r:
        body = r.read()
    return time.perf_counter() - t, json.loads(body)['external_api_calls'], body


class Command(BaseCommand):
    help = ('Latency, compute and fuel-cost benchmark over 12 US routes. Run with the server\'s CACHE_DIR: the '
            'in-process phases read the routes the HTTP phase cached.')

    def add_arguments(self, parser):
        parser.add_argument('--url', default='http://127.0.0.1:8000')
        parser.add_argument('--clear', action='store_true', help='clear the shared cache first (true cold run)')
        parser.add_argument('--write', action='store_true', help=f'also write {DOC.name} to the docs')

    def handle(self, *args, url, clear, write, **opts):
        if clear:
            cache.clear()
        cold, cached, variant, calls, size = {}, {}, [], Counter(), {}
        for i, (a, b) in enumerate(PAIRS):
            if i:
                time.sleep(COLD_GAP)
            cold[a, b], n, body = get(url, a, b)
            calls['cold', n] += 1
            size[a, b] = len(body), len(gzip.compress(body))
            self.stderr.write(f'cold {a} -> {b}: {ms(cold[a, b])} ms, {n} call(s)')
        for a, b in PAIRS:
            cached[a, b] = []
            for _ in range(CACHED_REPEATS):
                t, n, _ = get(url, a, b)
                cached[a, b].append(t)
                calls['cached', n] += 1
            for p in PENALTIES:
                t, n, _ = get(url, a, b, stop_penalty=p)
                variant.append(t)
                calls['penalty', n] += 1

        def no_route(*a, **k):
            raise CommandError('route not in cache: run with the same CACHE_DIR as the server')
        geo.get_route = no_route
        stage, routes = {k: [] for k in ('resolve', 'cache', 'stations_along', 'optimizer', 'serialize', 'total')}, {}
        for a, b in PAIRS:
            for _ in range(CACHED_REPEATS):
                t0 = time.perf_counter()
                s, f = geo.resolve(a), geo.resolve(b)
                t1 = time.perf_counter()
                leg, _ = views.leg(s, f)
                t2 = time.perf_counter()
                geo.stations_along(leg['line'])
                t3 = time.perf_counter()
                plan_fuel_stops(leg['corridor'], leg['distance_miles'], range_miles=views.RANGE_MILES)
                t4 = time.perf_counter()
                result, _ = views.plan(a, b)
                t5 = time.perf_counter()
                JsonResponse(result)
                t6 = time.perf_counter()
                for k, v in zip(stage, (t1 - t0, t2 - t1, t3 - t2, t4 - t3, t6 - t5, t6 - t4)):
                    stage[k].append(v)
            routes[a, b] = leg

        report = self.report(cold, cached, variant, calls, size, stage, routes)
        self.stdout.write(report)
        if write:
            DOC.write_text('---\ntitle: Benchmarks\ndescription: Latency, server-side compute, and fuel cost against '
                           'a naive fill-when-low driver on 12 US routes.\nicon: Timer\n---\n\n' + report)
            self.stderr.write(f'wrote {DOC}')

    def report(self, cold, cached, variant, calls, size, stage, routes):
        allcached = [t for ts in cached.values() for t in ts]
        raw, gz = [r for r, _ in size.values()], [g for _, g in size.values()]
        external = sum(n * c for (_, n), c in calls.items())
        dist = {ph: ', '.join(f'{n} call: {c}' for (p, n), c in sorted(calls.items()) if p == ph)
                for ph in ('cold', 'cached', 'penalty')}
        out = [
            f'Measured {datetime.date.today():%Y-%m-%d} from a dev laptop ({platform.system()} {platform.machine()}, '
            f'Python {platform.python_version()}) against the public OSRM demo server; network-dominated. '
            'gunicorn `-w 2 --threads 4 -k gthread` (the Docker image\'s config), `DEBUG=0`, a fresh file cache, '
            'one client, sequential requests.',
            '',
            f'Method: each route is requested once cold ({COLD_GAP} s apart; {external} external calls in the whole '
            f'run), then {CACHED_REPEATS} times cached, then once per `stop_penalty` in {list(PENALTIES)}. '
            'Compute stages are timed in-process on the cached routes. Percentiles are nearest-rank. Reproduce with '
            '`CACHE_DIR=<server cache> uv run python manage.py benchmark --url <server> --clear --write`.',
            '',
            '## Latency',
            '',
            '| Phase | Requests | p50 ms | p95 ms | max ms | `external_api_calls` |',
            '| --- | ---: | ---: | ---: | ---: | --- |',
        ]
        for name, ts, ph in (('Cold (first request)', list(cold.values()), 'cold'),
                             ('Cached (same request)', allcached, 'cached'),
                             ('`stop_penalty` variant', variant, 'penalty')):
            out.append(f'| {name} | {len(ts)} | {ms(pct(ts, .5))} | {ms(pct(ts, .95))} | {ms(max(ts))} | {dist[ph]} |')
        out += [
            '',
            f'Response JSON: median {statistics.median(raw) / 1024:.0f} KB raw, {statistics.median(gz) / 1024:.0f} '
            f'KB gzip; largest {max(raw) / 1024:.0f} KB raw, {max(gz) / 1024:.0f} KB gzip (Caddy compresses in '
            'production).',
            '',
            '## Server-side compute',
            '',
            'p50 over all cached requests, in-process (no HTTP). `stations_along` runs only on a cache miss; here it '
            'is timed on the cached response line (at most 5,000 points), a slight underestimate on long routes.',
            '',
            '| Stage | p50 ms | p95 ms |',
            '| --- | ---: | ---: |',
        ]
        labels = {'resolve': 'Resolve start + finish (Census table)', 'cache': 'Route cache read',
                  'stations_along': 'Corridor match (`stations_along`, cold path only)',
                  'optimizer': 'Optimizer (DP, $15 penalty)', 'serialize': 'JSON encode (`JsonResponse`)',
                  'total': 'Cached request total (resolve to JSON)'}
        out += [f'| {labels[k]} | {ms(pct(v, .5))} | {ms(pct(v, .95))} |' for k, v in stage.items()]
        out += [
            '',
            '## Per route',
            '',
            '| Route | Miles | Corridor stations | Cold ms | Cached p50 ms | JSON KB raw / gzip |',
            '| --- | ---: | ---: | ---: | ---: | ---: |',
        ]
        for (a, b), leg in routes.items():
            out.append(f'| {a} → {b} | {leg["distance_miles"]:,.0f} | {len(leg["corridor"])} | {ms(cold[a, b])} | '
                       f'{ms(pct(cached[a, b], .5))} | {size[a, b][0] / 1024:.0f} / {size[a, b][1] / 1024:.0f} |')
        out += [
            '',
            '## Fuel cost against a naive driver',
            '',
            f'Same corridor stations, same full tank at the start, {TANK}-mile range, {MPG} MPG. **Naive rule**: at '
            f'each corridor station in mile order, fill the tank to full if the finish is out of reach and the next '
            f'station (or the finish) would be reached with under {RESERVE} miles of fuel left; otherwise drive on. '
            'Fuel left in the tank at the finish is credited back at the last fill price. The optimizer is the '
            'service\'s DP at the default $15 stop penalty and at $0 (pure cheapest); the penalty is never counted '
            'as spend.',
            '',
            '| Route | Naive $ | Stops | Optimizer ($15) $ | Stops | Cheapest ($0) $ | Stops |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
        ]
        tot = [0.0] * 6
        for (a, b), leg in routes.items():
            row = [*naive(leg['corridor'], leg['distance_miles'])]
            for p in (15, 0):
                r = plan_fuel_stops(leg['corridor'], leg['distance_miles'], range_miles=views.RANGE_MILES,
                                    stop_penalty=p)
                row += [r['total_cost'], len(r['stops'])]
            tot = [x + y for x, y in zip(tot, row)]
            out.append(f'| {a} → {b} | ' + ' | '.join(f'{v:,.2f}' if k % 2 == 0 else str(v)
                                                     for k, v in enumerate(row)) + ' |')
        out.append('| **Total** | ' + ' | '.join(f'**{v:,.2f}**' if k % 2 == 0 else f'**{v:.0f}**'
                                                  for k, v in enumerate(tot)) + ' |')
        out += [
            '',
            f'Optimizer saves **${tot[0] - tot[2]:,.2f} ({(tot[0] - tot[2]) / (tot[0] or 1):.1%})** against the naive '
            f'driver with {tot[3]:.0f} stops instead of {tot[1]:.0f}; pure cheapest saves ${tot[0] - tot[4]:,.2f} '
            f'({(tot[0] - tot[4]) / (tot[0] or 1):.1%}) but needs {tot[5]:.0f} stops.',
            '',
        ]
        return '\n'.join(out)

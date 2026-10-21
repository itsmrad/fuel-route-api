import random
from decimal import Decimal
from unittest import TestCase

from routing.optimizer import Unreachable, plan_fuel_stops


def brute_force(stations, total, rng):
    """Min cost (mpg=1, start full) by DP over (station, fuel in whole miles)."""
    pts = sorted(stations) + [(total, 0)]
    best = {rng - pts[0][0]: Decimal(0)} if pts[0][0] <= rng else {}
    for (mile, price), (nxt, _) in zip(pts, pts[1:]):
        new = {}
        for fuel, cost in best.items():
            for buy in range(rng - fuel + 1):
                left = fuel + buy - (nxt - mile)
                if left >= 0:
                    c = cost + buy * price
                    new[left] = min(new.get(left, c), c)
        best = new
    return min(best.values()) if best else None


class PlanFuelStopsTests(TestCase):
    def test_under_range_needs_no_stops(self):
        r = plan_fuel_stops([(100, 3.5, 'a'), (200, 3.0, 'b')], 400)
        self.assertEqual((r['stops'], r['total_cost'], r['cost_of_fuel_consumed']), ([], 0.0, 120.0))
        self.assertIsNone(plan_fuel_stops([], 400)['cost_of_fuel_consumed'])

    def test_cheap_ahead_buys_just_enough(self):
        r = plan_fuel_stops([(100, 4, 'a'), (550, 2, 'b')], 900)
        self.assertEqual([(s['payload'], s['gallons']) for s in r['stops']], [('a', 5.0), ('b', 35.0)])

    def test_expensive_ahead_fills_up(self):
        r = plan_fuel_stops([(100, 2, 'a'), (550, 4, 'b')], 900)
        self.assertEqual([(s['payload'], s['gallons']) for s in r['stops']], [('a', 10.0), ('b', 30.0)])

    def test_unreachable_gap(self):
        for stations, gap in [([(300, 3, 'a'), (900, 3, 'b')], (300.0, 900.0)), ([(600, 3, 'a')], (0.0, 600.0))]:
            with self.assertRaises(Unreachable) as cm:
                plan_fuel_stops(stations, 1000)
            self.assertEqual((cm.exception.gap_start_mile, cm.exception.gap_end_mile), gap)

    def test_exact_cost(self):
        stations = [(100, Decimal('4.00'), 'a'), (400, Decimal('3.00'), 'b'), (800, 3.5, 'c'), (1000, 5, 'd'),
                    (1300, 1, 'past the end')]
        r = plan_fuel_stops(stations, 1200)
        self.assertEqual([(s['payload'], s['gallons'], s['cost']) for s in r['stops']],
                         [('b', 40.0, 120.0), ('c', 30.0, 105.0)])
        self.assertEqual((r['total_gallons'], r['total_cost'], r['gallons_consumed']), (70.0, 225.0, 120.0))
        self.assertEqual(r['cost_of_fuel_consumed'], 385.71)  # 120 * 225 / 70

    def test_greedy_matches_brute_force(self):
        rnd = random.Random(7)
        for _ in range(300):
            total, rng = rnd.randint(5, 60), rnd.randint(8, 20)
            stations = [(rnd.randint(0, total), Decimal(rnd.randint(100, 500)) / 100) for _ in range(rnd.randint(0, 10))]
            optimal = brute_force(stations, total, rng)
            try:
                got = plan_fuel_stops([(m, p, None) for m, p in stations], total, rng, mpg=1)['total_cost']
            except Unreachable:
                got = None
            self.assertEqual(got, None if optimal is None else float(optimal), (stations, total, rng))

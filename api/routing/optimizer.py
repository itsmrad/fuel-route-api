import math
from decimal import ROUND_HALF_UP, Decimal

STOP_PENALTY = 15.0  # USD per stop, roughly 30 min of driver time


class Unreachable(Exception):
    def __init__(self, gap_start_mile, gap_end_mile):
        super().__init__(f'no fuel reachable between mile {gap_start_mile} and {gap_end_mile}')
        self.gap_start_mile, self.gap_end_mile = gap_start_mile, gap_end_mile


def _d(x):
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _r(x, places):
    return float(x.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP))


def plan_fuel_stops(stations, total_miles, range_miles=500, mpg=10, start_fuel_miles=None, stop_penalty=STOP_PENALTY):
    """Min fuel cost + stop_penalty per stop over (mile, price, payload) stations, by DP over (station, fuel).

    dp[f] = cheapest way to arrive with f whole miles of fuel. At a station, either drive on or pay the penalty
    and fill from some f0 <= f up to f; min over f0 of dp[f0] - price*f0 is a running minimum, so a station costs
    O(range) and the trip O(stations x range). Positions round up to whole miles, so every plan is feasible.
    cost_of_fuel_consumed = trip gallons x average price paid, or the cheapest corridor price if nothing was bought.
    """
    total, mpg, F, inf = _d(total_miles), _d(mpg), int(range_miles), math.inf
    pts = sorted(((float(m), _d(p), s) for m, p, s in stations if 0 <= _d(m) <= total), key=lambda t: t[0])
    cheapest = min((p for _, p, _ in pts), default=None)
    dp = [inf] * (F + 1)
    dp[min(F, int(F if start_fuel_miles is None else start_fuel_miles))] = 0.0
    pos, prev, back = 0, 0.0, []
    for m, p, s in pts + [(float(total), None, None)]:
        here = math.ceil(m)
        d, pos = here - pos, here
        dp = dp[d:] + [inf] * min(d, F + 1)  # drive d miles: f -> f - d
        if min(dp) == inf:
            raise Unreachable(prev, m)
        if p is None:
            break
        new, came_from = dp[:], list(range(F + 1))
        price, best, arg = float(p), inf, 0
        for f in range(math.floor(m + F) - here + 1):  # tank cap, measured from the rounded-up position
            v = dp[f] - price * f
            if v < best:
                best, arg = v, f
            v = best + price * f + stop_penalty
            if v < new[f]:
                new[f], came_from[f] = v, arg
        dp, prev = new, m
        back.append((m, p, s, here, came_from))

    f, stops = min(range(F + 1), key=dp.__getitem__), []
    for m, p, s, here, came_from in reversed(back):
        f += pos - here  # fuel when leaving this station
        bought, f, pos = f - came_from[f], came_from[f], here
        if bought:
            gallons = Decimal(bought) / mpg
            stops.append({'mile': _d(m), 'price': p, 'gallons': gallons, 'cost': gallons * p, 'payload': s})
    stops.reverse()

    total_gallons = sum((s['gallons'] for s in stops), Decimal(0))
    total_cost = sum((s['cost'] for s in stops), Decimal(0))
    consumed = total / mpg
    avg = total_cost / total_gallons if total_gallons else cheapest
    return {
        'stops': [{'mile': _r(s['mile'], 1), 'price': _r(s['price'], 3), 'gallons': _r(s['gallons'], 3),
                   'cost': _r(s['cost'], 2), 'payload': s['payload']} for s in stops],
        'total_gallons': _r(total_gallons, 3),
        'total_cost': _r(total_cost, 2),
        'gallons_consumed': _r(consumed, 3),
        'cost_of_fuel_consumed': None if avg is None else _r(consumed * avg, 2),
    }

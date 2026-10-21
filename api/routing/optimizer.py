from decimal import ROUND_HALF_UP, Decimal


class Unreachable(Exception):
    def __init__(self, gap_start_mile, gap_end_mile):
        super().__init__(f'no fuel reachable between mile {gap_start_mile} and {gap_end_mile}')
        self.gap_start_mile, self.gap_end_mile = gap_start_mile, gap_end_mile


def _d(x):
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _r(x, places):
    return float(x.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP))


def plan_fuel_stops(stations, total_miles, range_miles=500, mpg=10, start_fuel_miles=None):
    """Greedy "to fill or not to fill" over (mile, price, payload) stations; optimal on a line.

    cost_of_fuel_consumed = trip gallons x average price paid, or the cheapest corridor price if nothing was bought.
    """
    total, rng, mpg = _d(total_miles), _d(range_miles), _d(mpg)
    fuel = rng if start_fuel_miles is None else _d(start_fuel_miles)
    pts = sorted(((_d(m), _d(p), s) for m, p, s in stations if 0 <= _d(m) <= total), key=lambda t: t[0])
    cheapest = min((p for _, p, _ in pts), default=None)
    pts.append((total, Decimal(0), None))  # destination: free fuel, so never worth arriving with a surplus
    if pts[0][0] > fuel:
        raise Unreachable(0.0, float(pts[0][0]))
    fuel -= pts[0][0]
    stops, i = [], 0
    while i < len(pts) - 1:
        mile, price, payload = pts[i]
        cheaper = best = None
        j = i + 1
        while j < len(pts) and pts[j][0] - mile <= rng:
            if pts[j][1] < price:
                cheaper = j
                break
            if best is None or pts[j][1] < pts[best][1]:
                best = j
            j += 1
        if cheaper is None and best is None:
            raise Unreachable(float(mile), float(pts[i + 1][0]))
        nxt = best if cheaper is None else cheaper
        buy = max((rng if cheaper is None else pts[nxt][0] - mile) - fuel, Decimal(0))
        if buy:
            gallons = buy / mpg
            stops.append({'mile': mile, 'price': price, 'gallons': gallons, 'cost': gallons * price, 'payload': payload})
        fuel += buy - (pts[nxt][0] - mile)
        i = nxt

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

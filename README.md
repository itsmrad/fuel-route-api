# Fuel Route API

[![CI](https://github.com/itsmrad/fuel-route-api/actions/workflows/ci.yml/badge.svg)](https://github.com/itsmrad/fuel-route-api/actions/workflows/ci.yml)

Django API: give it a start and finish in the USA, get back the driving route, the cost-optimal fuel stops for a 500-mile-range, 10 MPG truck, and the total fuel cost. One external call per request, zero on a cache hit.

Live docs and demo: (deployment URL — added in deploy step)

## Assignment requirements

| Requirement | How it is met | Where |
| --- | --- | --- |
| Start and finish within the USA | `"City, ST"` and `"lat,lon"` resolve locally against the Census Gazetteer; other text falls back to Nominatim. Non-US input is a 400. | `api/routing/geo.py` |
| Return a map of the route | `map_url` in every response opens a Leaflet page with the route and numbered stops; the GeoJSON line is also in the JSON. | `/api/route/map/`, `templates/routing/map.html` |
| Optimal fuel stops, cost-effective by price | Dynamic program over (station, fuel level): minimises fuel cost plus a per-stop penalty. | `api/routing/optimizer.py` |
| 500-mile range, multiple stops | Range is a hard constraint; stops are chosen along the whole route. Gaps over 500 mi return 422. | `optimizer.py` |
| Total money spent at 10 MPG | `total_fuel_cost` (fuel bought on the way) and `cost_of_fuel_consumed` (all fuel used). Money math in `Decimal`. | `optimizer.py` |
| Use the provided price file | Deduplicated and geocoded once by `manage.py load_stations`. | `api/data/fuel-prices.csv` |
| Free routing API, few calls | OSRM public server, one call returns geometry, distance and duration. `vehicle=truck` uses Valhalla truck costing (opt-in, see Limits). | `geo.get_route` |
| Fast | Cold ~0.9 s (almost all OSRM), cached 15–40 ms. | see Performance |
| Latest Django | Django 6.1, plain `JsonResponse`, no DRF. | `api/pyproject.toml` |

## Quickstart

With Docker: `docker compose up` → docs and route planner on http://localhost:3000, API on http://localhost:8000 (first build ~5 min; the image ships with the station data loaded).

Without Docker: needs [uv](https://docs.astral.sh/uv/) (installs Python 3.14 itself) and Node 20+ for the docs.

```bash
# API on http://127.0.0.1:8000
cd api && uv sync && uv run python manage.py migrate && uv run python manage.py load_stations && uv run python manage.py runserver

# Docs + route planner on http://localhost:3000 (proxies /api/* to :8000)
cd docs && npm install && npm run dev
```

`load_stations` downloads the Census Gazetteer once (~10 s) and prints coverage: `matched: 6443 (97.2%)`.

Postman: import [`postman_collection.json`](postman_collection.json) (12 requests with tests; `baseUrl` defaults to `http://127.0.0.1:8000`).

## API

`GET /api/route/?start=<loc>&finish=<loc>[&stop_penalty=<usd>][&vehicle=car|truck]` · `GET /api/route/map/?…` (HTML) · `GET /api/openapi.yaml` (OpenAPI 3.1)

```bash
curl -s 'http://127.0.0.1:8000/api/route/?start=Dallas,%20TX&finish=Chicago,%20IL'
```

Real response, route coordinates trimmed:

```json
{
  "start": { "query": "Dallas, TX", "lat": 32.7933, "lon": -96.7665 },
  "finish": { "query": "Chicago, IL", "lat": 41.837, "lon": -87.6849 },
  "distance_miles": 961.0,
  "duration_hours": 17.0,
  "routing": { "provider": "osrm", "profile": "car", "fallback": false },
  "fuel_stops": [
    { "mile": 161.6, "name": "EXTRA MILE TRUCK STOP", "address": "I-30 EXIT 208", "city": "Hooks", "state": "TX",
      "lat": 33.4707, "lon": -94.2865, "price": 2.817, "gallons": 16.1, "cost": 45.36 },
    { "mile": 648.0, "name": "HUCKS FOOD & FUEL #379", "address": "I-57, EXIT 53", "city": "Marion", "state": "IL",
      "lat": 37.7344, "lon": -88.9412, "price": 2.929, "gallons": 30.1, "cost": 88.16 }
  ],
  "total_gallons_purchased": 46.2,
  "total_fuel_cost": 133.52,
  "cost_of_fuel_consumed": 277.74,
  "stop_penalty": 15.0,
  "route": { "type": "LineString", "coordinates": [[-96.76642, 32.79325], [-96.76619, 32.79338], "…"] },
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=Dallas%2C+TX&finish=Chicago%2C+IL&stop_penalty=15.0&vehicle=car",
  "external_api_calls": 1
}
```

Errors are JSON `{"error", "detail"}`: `400` missing/invalid parameter or unknown/non-US location, `422` a gap longer than 500 mi with no station, `502` routing provider down.

Assumption: the truck starts with a full tank, so `total_fuel_cost` is fuel bought on the way (0 for trips under 500 mi); `cost_of_fuel_consumed` prices every gallon burned.

## How it works

1. **Resolve** start and finish: Census table or `lat,lon` locally (0 calls), else Nominatim (+1 each).
2. **Route** with OSRM `/route/v1/driving`: 1 call, full geometry. `vehicle=truck`: Valhalla `costing=truck` (Class 8: 4.11 m, 2.6 m, 21.64 m, 36.3 t); on failure or over the public server's 1,500 km cap, OSRM car with `routing.fallback: true`. OSRM demo server down or slow: one call to the FOSSGIS OSRM server (`fallback: true`). No retries; each call is cut off after 8 s wall clock, so a dead or slow provider costs at most 8 s.
3. **Corridor match**: in-memory 0.5° grid index keeps stations within 10 mi of the polyline, each with a mile marker.
4. **Optimize** stops (below).
5. **Respond**. The route (distance, line, corridor) is cached on the vehicle and resolved coordinates, so another spelling or `stop_penalty` re-runs only the optimizer; the map page reads the same entry.

External call budget: **1** typical, **0** cached; worst case ≤ 3 routing calls (Valhalla, OSRM demo, FOSSGIS) plus 1 per Nominatim lookup. Reported per response as `external_api_calls`.

## Optimizer

Minimises **fuel cost + `stop_penalty` × stops** (default **$15**, about 30 min of driver time) with a DP over (station, fuel on arrival in whole miles, 0–500): O(n · 501). With `stop_penalty=0` the classic greedy ("fill up if nothing cheaper is in range, else buy just enough to reach the cheaper one") is already optimal; the DP exists because free stops make greedy chase cents.

| NYC → LA | Stops | Fuel cost |
| --- | --- | --- |
| `stop_penalty=0` | 16 | $698.92 |
| default ($15) | **7** | **$702.79** |

Nine fewer stops for +$3.87. The penalty only steers the choice; it is never added to `total_fuel_cost`. Tests check the DP against brute force.

## Performance

| Stage | Time |
| --- | --- |
| Cold request | ~0.8–0.9 s (Dallas → Chicago, NYC → LA, Miami → Seattle), dominated by the OSRM call |
| Cached route (optimizer re-runs) | 15–40 ms |
| Corridor match | 18–30 ms |
| DP (NYC → LA, 447 stations) | ~22 ms |

## Data and geocoding

The CSV has no coordinates and addresses like `I-44, EXIT 283 & US-69`. `load_stations` dedupes 8,151 rows to 6,738 stations, keeps **6,626 US** ones, and places **97.2%** (6,443) at their city centroid via the US Census 2024 Gazetteer (places + county subdivisions, name normalization, consolidated-city aliases). Unmatched rows are logged and dropped.

- **City centroid, not the exit**: mile markers can be off by a few miles; the 10-mile corridor absorbs most of it.
- **California gap**: only 8 CA stations, all near the Mexican border, so NYC → LA has no station for its last ~273 mi (fine within range, fewer choices out West).

## Tests

```bash
cd api && uv run python manage.py test   # 36 tests, no network (OSRM/Valhalla mocked)
```

Optimizer cases (cheap-ahead, fill-up, short trip, unreachable gap, exact cents, DP vs brute force), geocoding, and the endpoint (asserts 1 external call, then 0 on repeat).

## Layout

```
api/                     Django project (uv)
  config/                settings, urls
  routing/
    geo.py               resolve location, OSRM client, stations along route
    optimizer.py         plan_fuel_stops() DP
    views.py             /api/route/, /api/route/map/, /api/openapi.yaml
    management/commands/load_stations.py
    templates/routing/map.html
    test_*.py
  data/fuel-prices.csv
  openapi.yaml           OpenAPI 3.1 spec (served at /api/openapi.yaml)
docs/                    Fumadocs (Next.js): guides, route planner, API reference
postman_collection.json
plan.md                  design notes
```

## Limits and upgrade path

| Limit | Upgrade |
| --- | --- |
| Stations at city centroid | Geocode station addresses once, offline |
| Public OSRM servers (best-effort, ~1 req/s; FOSSGIS is the fallback) | Self-hosted OSRM or OpenRouteService; one-function swap in `get_route` |
| Truck routing opt-in: public Valhalla caps trips at 1,500 km, so coast-to-coast falls back to OSRM car | Self-hosted Valhalla, then default `vehicle=truck` |
| Sparse West Coast data | Fuller price feed; optimizer unchanged |
| Price snapshot | Scheduled `load_stations` from a live feed |
| File cache, one box | Redis when there is more than one box |
| In-memory grid index | PostGIS + GiST past a few hundred thousand stations |
| Fixed 500 mi / 10 MPG, full tank at start | `range`, `mpg`, `start_fuel` query parameters |

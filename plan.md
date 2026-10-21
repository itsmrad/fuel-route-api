# Fuel Route API: Implementation Plan

Django API: start and finish locations in the USA → a route map, cost-optimal fuel stops (500 mi range, 10 mpg), and the total fuel cost.

---

## 1. Decisions already made

| Topic | Decision |
|---|---|
| Starting fuel | **Full tank (500 mi).** "Total cost" = fuel bought at stops. The response also reports `cost_of_fuel_consumed` (gallons used × average price paid) so trips under 500 mi still show a meaningful number. |
| Input | `"City, ST"` or `"lat,lon"` → resolved **locally** (0 API calls). Anything else → Nominatim fallback (+1 call per location). |
| External calls per request | **1** typical (OSRM), **3** worst case (2 Nominatim + 1 OSRM), **0** on a cache hit. |
| Hosting | AWS Lightsail (Ubuntu), gunicorn + Caddy (automatic HTTPS). |
| Git flow | `main` = scaffolding only → one feature branch per step → push → PR via `gh` → CodeRabbit / Kilo Code review → address comments → merge via `gh`. |

## 2. Findings from the data (verified)

- `fuel-prices-for-be-assessment.csv`: 8,151 rows, **6,738 unique stations** (duplicate IDs), 3,893 city/state pairs, prices $2.69–$6.40.
- **No coordinates in the CSV.** Addresses look like `I-44, EXIT 283 & US-69`, which can't be geocoded reliably.
- Matching city/state against the **US Census 2024 Gazetteer (places)** matches **91%** of cities offline. The misses are:
  - Canadian rows (BC, ON, AB, SK…) → out of scope, dropped.
  - New England towns → covered by the Census **county subdivisions** Gazetteer file.
  - Consolidated cities (Athens-Clarke, Augusta-Richmond, Boise City) → handled by normalizing name suffixes and prefix matching.
  - Any remaining misses are logged and dropped. Expected coverage is above 97%.
- The OSRM public server works without a key (tested: NYC→Chicago, 1,272 km).

## 3. Architecture

```
GET /api/route/?start=Dallas, TX&finish=Chicago, IL
  1. resolve start/finish      local Census table → else Nominatim
  2. route                     OSRM /route/v1/driving (1 call, full GeoJSON geometry)
  3. stations near route       in-memory grid index (0.5° cells), keep stations ≤ 10 mi
                               from the polyline; mile marker = cumulative distance of
                               the nearest route point
  4. optimize stops            greedy "fill or not to fill" (provably optimal on a line)
  5. respond                   JSON + map_url; result cached (key = normalized start|finish)

GET /api/route/map/?start=...&finish=...
  Leaflet + OSM tiles page; reads the cached result → 0 extra API calls
```

### Optimizer (core logic)
Stations are sorted by mile marker; the destination is a virtual station with price 0.
- At position *p* with fuel *f*: look ahead 500 mi.
  - If a **cheaper** station is reachable → buy just enough to reach the first one, then go there.
  - Otherwise → **fill up** here and go to the **cheapest** station in range.
  - If no station is in range and the destination is too far → return a 422 `unreachable` error naming the gap.
- Complexity is O(n·k), with n = stations on the route (low hundreds), so it runs in under 1 ms.

### Why each piece is the simplest thing that works
- **Plain Django + `JsonResponse`** for one endpoint; no DRF.
- **SQLite + `Station` model + `manage.py load_stations`**: idiomatic Django, data loaded once into memory on first request.
- **Stdlib grid index** instead of PostGIS, scipy or numpy. 6.7k points don't need a spatial DB.
- **Django locmem cache** instead of Redis, since there is one server.
- **`requests`** is the only third-party dependency beyond Django and gunicorn.

### Known limits (stated in the README, with a `ponytail:` comment in code)
- Station position = city centroid (a few miles of error). Upgrade path: geocode station addresses once, offline.
- The OSRM demo server is best-effort and limited to 1 req/s. Upgrade path: self-hosted OSRM or OpenRouteService (free key), a one-function swap.

## 4. API contract

`GET /api/route/?start=<loc>&finish=<loc>`

```json
{
  "start":  {"query": "Dallas, TX", "lat": 32.78, "lon": -96.80},
  "finish": {"query": "Chicago, IL", "lat": 41.88, "lon": -87.63},
  "distance_miles": 925.4,
  "duration_hours": 13.6,
  "fuel_stops": [
    {"mile": 412.3, "name": "PILOT #123", "address": "I-44, EXIT 283", "city": "Big Cabin",
     "state": "OK", "lat": 36.53, "lon": -95.22, "price": 3.007,
     "gallons": 31.2, "cost": 93.82}
  ],
  "total_gallons_purchased": 42.5,
  "total_fuel_cost": 128.40,
  "cost_of_fuel_consumed": 279.10,
  "route": {"type": "LineString", "coordinates": [[-96.80, 32.78], "..."]},
  "map_url": "https://<host>/api/route/map/?start=Dallas%2C+TX&finish=Chicago%2C+IL",
  "external_api_calls": 1
}
```
Errors: `400` (missing input, unknown or non-US location), `422` (unreachable gap of more than 500 mi), `502` (routing provider down).

## 5. Repo layout (deliberately small)

```
fuel-route-api/
  manage.py
  requirements.txt            django, requests, gunicorn
  config/                     settings.py, urls.py, wsgi.py
  routing/
    models.py                 Station
    management/commands/load_stations.py
    geo.py                    resolve location, OSRM call, stations-near-route
    optimizer.py              plan_fuel_stops()
    views.py                  route_api, route_map
    templates/routing/map.html
    tests.py
  data/fuel-prices.csv        (Census files downloaded by load_stations, gitignored)
  deploy/                     Caddyfile, fuel-route.service, deploy.sh
  postman_collection.json
  README.md
```

## 6. Git workflow (branch by branch)

Prerequisites: `gh auth status` OK; CodeRabbit and/or Kilo Code GitHub app installed on the new repo.

| # | Branch | Contents | Done when |
|---|---|---|---|
| 0 | `main` | `django-admin startproject`, `.gitignore`, `requirements.txt`, README stub | First push; repo `fuel-route-api` created via `gh repo create` (public) |
| 1 | `feat/station-data` | `Station` model, migration, `load_stations` (CSV dedupe → Census geocode), unmatched-city report | Command loads ~6.5k US stations |
| 2 | `feat/routing` | `geo.py`: local resolver + Nominatim fallback, OSRM client (User-Agent, timeout), stations-near-route | Dallas→Chicago returns route + corridor stations |
| 3 | `feat/fuel-optimizer` | `optimizer.py` + unit tests (cheap-ahead, fill-up, under-500 mi, unreachable gap, exact cost math) | Tests green |
| 4 | `feat/api-endpoint` | Views, URLs, cache, Leaflet map page, endpoint test with OSRM mocked (asserts 1 call, then 0 on repeat) | Postman returns JSON; map renders |
| 5 | `docs/readme-postman` | README (setup in 3 commands, assumptions, call budget, limits), Postman collection | Fresh clone works by following the README |
| 6 | `deploy/lightsail` | Prod settings via env vars, gunicorn systemd unit, Caddyfile, `deploy.sh` | Live HTTPS URL in README |

Per branch: commit in small logical steps → `git push -u` → `gh pr create` → wait for the CodeRabbit/Kilo review (`gh pr view --comments`) → fix valid comments and reply to the rest → `gh pr merge --squash --delete-branch`.

## 7. Deployment (AWS Lightsail)

1. Lightsail instance: Ubuntu 24.04, smallest plan ($5/mo is enough), static IP attached, ports 80/443 open.
2. On the box: `python3 -m venv`, `pip install -r requirements.txt`, `migrate`, `load_stations`, `collectstatic`.
3. `gunicorn config.wsgi -w 3 -b 127.0.0.1:8000` under systemd.
4. Caddy reverse proxy with automatic HTTPS. With no domain, use `<ip>.sslip.io` for a free valid certificate.
5. `DEBUG=False`, `SECRET_KEY`, and `ALLOWED_HOSTS` set from an env file; simple per-IP throttle in Caddy to protect the free OSRM quota.
6. `deploy/deploy.sh`: `git pull && pip install && migrate && systemctl restart`.

**Needed from you:** either (a) an IAM user's access keys scoped to Lightsail, so I create the instance with the AWS CLI, or (b) an instance you create, plus its SSH key path and IP. Option (b) is safer because I never hold AWS keys. Optionally, a domain name.

## 8. Testing and performance targets
- `python manage.py test`: optimizer cases + endpoint (OSRM mocked, no network).
- Targets: cold request under 1.5 s (dominated by OSRM), cached request under 50 ms, compute part under 50 ms.
- Manual cross-country check: NYC→LA (~2,800 mi, 5+ stops), Miami→Seattle, a short trip (Austin→Dallas, 0 stops).

## 9. Loom script (≤ 5 min)
1. **0:00–0:30** The problem, plus the 3 key choices: OSRM, offline Census geocoding, the greedy optimizer.
2. **0:30–2:00** Postman: NYC→LA. Walk through stops, prices, total cost, `external_api_calls: 1`, response time; repeat the request to show the cache (about 20 ms); open `map_url` in a browser.
3. **2:00–2:30** Error cases: unknown city (400), short trip (0 stops).
4. **2:30–4:30** Code tour: `load_stations` → `geo.py` (one OSRM call, grid index) → `optimizer.py` (why greedy is optimal) → `views.py` (cache).
5. **4:30–5:00** Limits and the upgrade path (station geocoding, self-hosted OSRM, PostGIS).

## 10. Open items before starting
- [ ] Confirm `gh` is logged into the GitHub account that should own the repo.
- [ ] CodeRabbit / Kilo Code installed for that account or repo.
- [ ] AWS access: option (a) or (b) from section 7.

---
Sources: [OSRM API usage policy](https://github.com/Project-OSRM/osrm-backend/wiki/API%20Usage%20Policy) · [OpenRouteService plans](https://openrouteservice.org/plans/) · [Census Gazetteer 2024](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2024.html) · [Django downloads](https://www.djangoproject.com/download/)

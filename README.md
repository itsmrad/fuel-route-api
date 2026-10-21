# fuel-route-api

Django API that takes a start and finish location in the USA and returns the route, cost-optimal fuel stops (500 mi range, 10 mpg) based on the provided fuel price data, and the total fuel cost. See [plan.md](plan.md) for the design.

## Layout

Monorepo:

- `api/`: Django project (`manage.py`, `config/`, `routing/`, `data/`, `requirements.txt`)
- `docs/`: Fumadocs (Next.js) docs site with an interactive route planner and API reference (coming)
- `deploy/`: Caddyfile, systemd units, `deploy.sh` (coming)

## Setup

```sh
cd api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate && .venv/bin/python manage.py load_stations
```

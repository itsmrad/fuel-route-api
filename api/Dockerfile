FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/
# Lambda Web Adapter: lets this image run as-is on AWS Lambda (an extension, inert under docker compose).
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependencies first, so code edits don't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

COPY . .
RUN useradd --system app && chown app /app /app/data
USER app

# Bake the database into the image: migrate + load_stations (downloads the Census Gazetteer once, ~10 s).
RUN python manage.py migrate && python manage.py load_stations

EXPOSE 8000
# Requests mostly wait on OSRM, so threads beat processes.
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000", "-w", "2", "--threads", "4", "-k", "gthread", "--access-logfile", "-"]

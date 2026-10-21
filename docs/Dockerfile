FROM node:24-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/docs
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
# The API reference is generated from ../api/openapi.yaml (compose passes ./api as the "api" context).
COPY --from=api openapi.yaml /app/api/openapi.yaml
COPY . .
# Rewrites to the API are baked into the build output, so the target is a build arg.
ARG API_ORIGIN=http://api:8000
RUN npm run build && npm prune --omit=dev && rm -rf .next/cache

FROM node:24-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node /app /app
WORKDIR /app/docs
USER node
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]

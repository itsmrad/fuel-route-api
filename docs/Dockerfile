FROM node:24-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/docs
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
# The API reference is generated from ../api/openapi.yaml (compose passes ./api as the "api" context).
COPY --from=api openapi.yaml /app/api/openapi.yaml
COPY . .
# Absolute Open Graph image URLs (app/layout.tsx); localhost when unset.
ARG SITE_URL
RUN npm run build

# Standalone output: server.js plus only the traced node_modules.
FROM node:24-slim
# Lambda Web Adapter: lets this image run as-is on AWS Lambda (an extension, inert under docker compose).
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app/docs
# lib/openapi.ts resolves ../api/openapi.yaml from the cwd if a page renders on demand.
COPY --from=api openapi.yaml /app/api/openapi.yaml
COPY --from=build --chown=node /app/docs/.next/standalone ./
COPY --from=build --chown=node /app/docs/.next/static ./.next/static
COPY --from=build --chown=node /app/docs/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]

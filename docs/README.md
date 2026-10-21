# Fuel Route API docs

Fumadocs (Next.js) site: guides, an interactive route planner and the API reference generated from `../api/openapi.yaml`.

- Install: `npm install`
- Dev: `npm run dev` (http://localhost:3000; `/api/*` proxies to `API_ORIGIN`, default `http://127.0.0.1:8000`)
- Build: `npm run build && npm start`
- Regenerate the API reference after editing the spec: `npm run gen:api`

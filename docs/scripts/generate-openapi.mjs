// Regenerates content/docs/api/*.mdx from ../api/openapi.yaml: `npm run gen:api`.
import { generateFiles } from 'fumadocs-openapi';
import { createOpenAPI } from 'fumadocs-openapi/server';

await generateFiles({
  input: createOpenAPI({ input: ['../api/openapi.yaml'] }),
  output: './content/docs/api',
  per: 'operation',
  includeDescription: true,
  // planRoute.mdx -> plan-route.mdx
  beforeWrite(files) {
    for (const f of files) f.path = f.path.replace(/([a-z])([A-Z])/g, '$1-$2').toLowerCase();
  },
});

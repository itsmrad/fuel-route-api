// Regenerates content/docs/api/*.mdx from ../api/openapi.yaml: `npm run gen:api`.
import { generateFiles } from 'fumadocs-openapi';
import { createOpenAPI } from 'fumadocs-openapi/server';

await generateFiles({
  input: createOpenAPI({ input: ['../api/openapi.yaml'] }),
  output: './content/docs/api',
  per: 'operation',
  includeDescription: true,
  // The body shows the full description; frontmatter gets its first sentence, as plain text,
  // for <meta name="description"> and the previous/next cards.
  frontmatter: (_title, description) =>
    description ? { description: description.replace(/`/g, '').replace(/\s+/g, ' ').trim().split(/(?<=\.) /)[0] } : {},
  // planRoute.mdx -> plan-route.mdx
  beforeWrite(files) {
    for (const f of files) f.path = f.path.replace(/([a-z])([A-Z])/g, '$1-$2').toLowerCase();
  },
});

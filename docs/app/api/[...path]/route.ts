import type { NextRequest } from 'next/server';

// Django serves the API. The browser only ever talks to this origin, so no CORS.
// A handler, not a next.config rewrite: a rewrite passes the API's x-amzn-* headers through,
// and a Lambda Function URL answers 502 to a response that carries them.
const apiOrigin = process.env.API_ORIGIN ?? 'http://127.0.0.1:8000';

export async function GET(req: NextRequest) {
  // pathname, not params: Django's URLs end in "/" and params drop it.
  const url = new URL(req.nextUrl.pathname + req.nextUrl.search, apiOrigin);
  let res: Response;
  try {
    res = await fetch(url, {
      cache: 'no-store',
      // Django builds map_url from these, so it points back at this origin.
      headers: {
        'x-forwarded-host': req.headers.get('host') ?? '',
        'x-forwarded-proto': req.headers.get('x-forwarded-proto') ?? 'http',
      },
    });
  } catch {
    // Plain text, so the planner reports "The API isn't running".
    return new Response(`No API at ${apiOrigin}`, { status: 502 });
  }
  const headers = new Headers(res.headers);
  for (const name of [...headers.keys()]) {
    if (name.startsWith('x-amzn-')) headers.delete(name);
  }
  return new Response(res.body, { status: res.status, headers });
}

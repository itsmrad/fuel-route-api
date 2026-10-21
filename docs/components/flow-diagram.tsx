type Box = { x: number; y: number; w: number; title: string; sub: string; external?: boolean };

const H = 50;
const ROW1 = 24;
const ROW2 = 160;

const boxes: Box[] = [
  { x: 8, y: ROW1, w: 140, title: 'Client', sub: 'browser · Postman' },
  { x: 180, y: ROW1, w: 150, title: 'Caddy', sub: '/api/* → gunicorn' },
  { x: 364, y: ROW1, w: 120, title: 'route_api', sub: 'Django view' },
  { x: 518, y: ROW1, w: 122, title: 'Cache', sub: 'file · per trip' },
  { x: 674, y: ROW1, w: 118, title: 'JSON', sub: '+ map_url' },
  { x: 8, y: ROW2, w: 170, title: 'resolve()', sub: 'Census table', external: false },
  { x: 214, y: ROW2, w: 170, title: 'OSRM / Valhalla', sub: '1 call · 0.6–2.3 s', external: true },
  { x: 420, y: ROW2, w: 170, title: 'stations_along()', sub: 'grid index · 18–30 ms' },
  { x: 626, y: ROW2, w: 166, title: 'optimizer', sub: 'DP · ~20 ms' },
];

function Node({ b }: { b: Box }) {
  return (
    <g>
      <rect
        x={b.x}
        y={b.y}
        width={b.w}
        height={H}
        rx={10}
        fill="var(--color-fd-card)"
        stroke={b.external ? 'var(--color-brand)' : 'var(--color-fd-border)'}
        strokeWidth={b.external ? 1.5 : 1}
      />
      <text x={b.x + 14} y={b.y + 21} fontSize="13.5" fontWeight="600" fill="currentColor">
        {b.title}
      </text>
      <text x={b.x + 14} y={b.y + 38} fontSize="11" fill="var(--color-fd-muted-foreground)" fontFamily="var(--font-mono)">
        {b.sub}
      </text>
    </g>
  );
}

function Arrow({ d, label, lx, ly, accent }: { d: string; label?: string; lx?: number; ly?: number; accent?: boolean }) {
  return (
    <g>
      <path
        d={d}
        fill="none"
        stroke={accent ? 'var(--color-brand)' : 'var(--color-fd-muted-foreground)'}
        strokeOpacity={accent ? 1 : 0.55}
        strokeWidth="1.5"
        markerEnd={accent ? 'url(#arrow-accent)' : 'url(#arrow)'}
      />
      {label && (
        <text x={lx} y={ly} fontSize="11" fontFamily="var(--font-mono)" fill={accent ? 'var(--color-brand)' : 'var(--color-fd-muted-foreground)'}>
          {label}
        </text>
      )}
    </g>
  );
}

/** Request flow for GET /api/route/ (cache hit on top, miss path below). */
export function FlowDiagram() {
  const r1 = ROW1 + H / 2;
  const r2 = ROW2 + H / 2;
  return (
    <figure className="not-prose my-6 overflow-x-auto rounded-2xl border bg-fd-background p-4">
      <svg viewBox="0 0 800 260" className="min-w-[680px] w-full text-fd-foreground" role="img" aria-labelledby="flow-title">
        <title id="flow-title">
          Request flow: client to Caddy to the Django view; a cache hit returns JSON with zero external calls; a miss resolves
          locations, calls the router (OSRM or Valhalla) once, finds stations along the route, runs the optimizer and caches the result.
        </title>
        <defs>
          {[
            ['arrow', 'var(--color-fd-muted-foreground)'],
            ['arrow-accent', 'var(--color-brand)'],
          ].map(([id, c]) => (
            <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill={c} />
            </marker>
          ))}
        </defs>

        <Arrow d={`M148 ${r1} H178`} />
        <Arrow d={`M330 ${r1} H362`} />
        <Arrow d={`M484 ${r1} H516`} />
        <Arrow d={`M640 ${r1} H672`} label="hit · 0 calls" lx={618} ly={ROW1 - 8} accent />
        <Arrow d={`M579 ${ROW1 + H} V112 H93 V${ROW2 - 2}`} label="miss" lx={548} ly={106} />
        <Arrow d={`M178 ${r2} H212`} />
        <Arrow d={`M384 ${r2} H418`} />
        <Arrow d={`M590 ${r2} H624`} />
        <Arrow d={`M729 ${ROW2} V${ROW1 + H + 2}`} label="cache.set" lx={737} ly={130} />

        {boxes.map((b) => (
          <Node key={b.title} b={b} />
        ))}

        <text x={8} y={ROW2 + H + 26} fontSize="11" fill="var(--color-fd-muted-foreground)">
          <tspan x={8}>&quot;City, ST&quot; or lat,lon: 0 calls.</tspan>
          <tspan x={8} dy="15">Anything else: Nominatim, +1 each.</tspan>
        </text>
        <text x={214} y={ROW2 + H + 26} fontSize="11" fill="var(--color-fd-muted-foreground)">
          <tspan x={214}>Full route geometry.</tspan>
          <tspan x={214} dy="15">Dominates a cold request.</tspan>
        </text>
        <text x={420} y={ROW2 + H + 26} fontSize="11" fill="var(--color-fd-muted-foreground)">
          <tspan x={420}>Stations ≤ 10 mi of the line,</tspan>
          <tspan x={420} dy="15">with a mile marker each.</tspan>
        </text>
        <text x={626} y={ROW2 + H + 26} fontSize="11" fill="var(--color-fd-muted-foreground)">
          <tspan x={626}>Fill or not to fill,</tspan>
          <tspan x={626} dy="15">Decimal money math.</tspan>
        </text>
      </svg>
      <figcaption className="mt-2 flex items-center gap-3 text-xs text-fd-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-5 rounded-[4px] border-[1.5px] border-brand" /> external service
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-5 rounded-[4px] border" /> in-process
        </span>
      </figcaption>
    </figure>
  );
}

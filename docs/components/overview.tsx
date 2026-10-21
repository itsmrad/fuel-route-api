import Link from 'next/link';
import { ArrowRight, Terminal } from 'lucide-react';

const SPECS = [
  ['1', 'external call per trip', 'OSRM routing; locations resolve locally'],
  ['6,443', 'stations', 'deduped from 8,151 CSV rows'],
  ['97.2%', 'geocoded offline', 'Census Gazetteer, no API'],
  ['0', 'calls on a repeat', 'responses cached per trip'],
] as const;

/** Overview hero: a route drawn across the header, the one-line pitch, and the spec sheet. */
export function Hero() {
  return (
    <section className="not-prose relative -mt-2 mb-10">
      <svg viewBox="0 0 600 120" className="pointer-events-none mb-6 h-20 w-full max-w-xl text-fd-foreground sm:h-24" aria-hidden>
        <path
          d="M10 96 C 90 96, 110 40, 190 44 S 290 100, 360 76 S 470 18, 590 22"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.18"
          strokeWidth="10"
          strokeLinecap="round"
        />
        <path
          d="M10 96 C 90 96, 110 40, 190 44 S 290 100, 360 76 S 470 18, 590 22"
          fill="none"
          stroke="var(--color-brand)"
          strokeWidth="3"
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray="1"
          style={{ ['--len' as string]: 1, animation: 'route-draw 1.6s cubic-bezier(0.16,1,0.3,1) both' }}
        />
        <circle cx="10" cy="96" r="7" fill="var(--color-fd-background)" stroke="currentColor" strokeWidth="2.5" />
        {[
          [190, 44],
          [360, 76],
        ].map(([cx, cy], i) => (
          <g key={i}>
            <circle cx={cx} cy={cy} r="11" fill="var(--color-brand)" />
            <text x={cx} y={cy + 4} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--color-fd-primary-foreground)" fontFamily="var(--font-mono)">
              {i + 1}
            </text>
          </g>
        ))}
        <circle cx="590" cy="22" r="7" fill="currentColor" />
      </svg>

      <h1 className="max-w-2xl text-4xl font-bold leading-[1.05] tracking-[-0.03em] text-balance sm:text-5xl">
        Where to fill up, from any US city to any other.
      </h1>
      <p className="mt-4 max-w-xl text-lg leading-relaxed text-fd-muted-foreground text-pretty">
        One Django endpoint takes a start and a finish, routes the trip, and picks the fuel stops that minimise cost for a truck
        with a 500-mile range at 10 MPG.
      </p>
      <div className="mt-6 flex flex-wrap gap-2.5">
        <Link
          href="/docs/route-planner"
          className="inline-flex h-10 items-center gap-2 rounded-xl bg-fd-primary px-4 text-sm font-semibold text-fd-primary-foreground transition hover:brightness-110"
        >
          Open the route planner <ArrowRight className="size-4" />
        </Link>
        <Link
          href="/docs/quickstart"
          className="inline-flex h-10 items-center gap-2 rounded-xl border px-4 text-sm font-medium transition-colors hover:bg-fd-accent"
        >
          <Terminal className="size-4 text-fd-muted-foreground" /> Run it locally
        </Link>
      </div>

      <dl className="mt-10 grid grid-cols-2 border-y sm:grid-cols-4">
        {SPECS.map(([value, label, note], i) => (
          <div key={label} className={`py-4 pr-4 ${i ? 'sm:border-l sm:pl-4' : ''} ${i % 2 ? 'max-sm:border-l max-sm:pl-4' : ''} ${i > 1 ? 'max-sm:border-t' : ''}`}>
            <dt className="sr-only">{label}</dt>
            <dd>
              <span className="block text-3xl font-bold tabular tracking-tight">{value}</span>
              <span className="mt-1 block text-sm font-medium">{label}</span>
              <span className="mt-0.5 block text-xs text-fd-muted-foreground">{note}</span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

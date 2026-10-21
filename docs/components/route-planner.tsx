'use client';
import dynamic from 'next/dynamic';
import { useState, useSyncExternalStore, type FormEvent, type ReactNode } from 'react';
import {
  ArrowRight,
  ArrowUpDown,
  CircleDot,
  CloudOff,
  ExternalLink,
  Loader2,
  MapPin,
  RouteOff,
  SearchX,
  ServerCrash,
  Zap,
} from 'lucide-react';
import type { ApiError, RoutePlan } from './route-types';

const RouteMap = dynamic(() => import('./route-map'), {
  ssr: false,
  loading: () => <div className="size-full animate-pulse bg-fd-muted" />,
});

const PRESETS = [
  { label: 'New York → Los Angeles', start: 'New York, NY', finish: 'Los Angeles, CA' },
  { label: 'Dallas → Chicago', start: 'Dallas, TX', finish: 'Chicago, IL' },
  { label: 'Miami → Seattle', start: 'Miami, FL', finish: 'Seattle, WA' },
  { label: 'Austin → Dallas', start: 'Austin, TX', finish: 'Dallas, TX' },
];

type Problem = { kind: 'bad-input' | 'unreachable' | 'upstream' | 'offline' | 'unknown'; status?: number; body?: ApiError };

type State =
  | { phase: 'idle' }
  | { phase: 'loading'; url: string }
  | { phase: 'done'; url: string; plan: RoutePlan; ms: number; status: number }
  | { phase: 'error'; url: string; problem: Problem; ms: number };

function subscribeTheme(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  return () => mo.disconnect();
}

function useDark() {
  return useSyncExternalStore(
    subscribeTheme,
    () => document.documentElement.classList.contains('dark'),
    () => true,
  );
}

async function planRoute(start: string, finish: string): Promise<State> {
  const url = `/api/route/?${new URLSearchParams({ start, finish })}`;
  const t0 = performance.now();
  let res: Response;
  try {
    res = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch {
    return { phase: 'error', url, ms: performance.now() - t0, problem: { kind: 'offline' } };
  }
  const isJson = res.headers.get('content-type')?.includes('application/json');
  const body = isJson ? await res.json().catch(() => null) : null;
  const ms = performance.now() - t0;
  if (res.ok && body) return { phase: 'done', url, plan: body as RoutePlan, ms, status: res.status };

  const status = res.status;
  // The Next.js proxy answers 500/502/504 with HTML when nothing listens on API_ORIGIN.
  if (!body) return { phase: 'error', url, ms, problem: { kind: status === 404 ? 'unknown' : 'offline', status } };
  const kind = status === 400 ? 'bad-input' : status === 422 ? 'unreachable' : status === 502 ? 'upstream' : 'unknown';
  return { phase: 'error', url, ms, problem: { kind, status, body: body as ApiError } };
}

const n0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const n1 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

function hours(h: number) {
  const whole = Math.floor(h);
  const m = Math.round((h - whole) * 60);
  return m ? `${whole}h ${m}m` : `${whole}h`;
}

export function RoutePlanner() {
  const [start, setStart] = useState(PRESETS[1].start);
  const [finish, setFinish] = useState(PRESETS[1].finish);
  const [state, setState] = useState<State>({ phase: 'idle' });
  const [focus, setFocus] = useState<{ i: number; at: number } | null>(null);
  const dark = useDark();

  async function run(s = start, f = finish) {
    setStart(s);
    setFinish(f);
    setFocus(null);
    setState({ phase: 'loading', url: `/api/route/?${new URLSearchParams({ start: s, finish: f })}` });
    setState(await planRoute(s.trim(), f.trim()));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void run();
  }

  const busy = state.phase === 'loading';

  return (
    <div className="not-prose my-6 flex flex-col gap-4">
      <form
        onSubmit={onSubmit}
        className="rounded-2xl border bg-fd-card p-3 shadow-[0_1px_0_rgb(0_0_0/0.02),0_8px_24px_-16px_rgb(0_0_0/0.25)] sm:p-4"
      >
        <div className="flex flex-col gap-2 md:flex-row md:items-stretch">
          <div className="relative flex flex-1 flex-col gap-2 sm:flex-row">
            <Field icon={<CircleDot className="size-4" />} label="Start" value={start} onChange={setStart} />
            <button
              type="button"
              onClick={() => {
                setStart(finish);
                setFinish(start);
              }}
              aria-label="Swap start and finish"
              className="absolute right-3 top-1/2 z-10 grid size-7 -translate-y-1/2 place-items-center rounded-full border bg-fd-background text-fd-muted-foreground transition-colors hover:text-fd-foreground sm:static sm:size-auto sm:translate-y-0 sm:self-center sm:border-0 sm:bg-transparent sm:p-1"
            >
              <ArrowUpDown className="size-3.5 sm:rotate-90" />
            </button>
            <Field icon={<MapPin className="size-4" />} label="Finish" value={finish} onChange={setFinish} />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-fd-primary px-5 text-sm font-semibold text-fd-primary-foreground transition-[filter,transform] hover:brightness-110 active:translate-y-px disabled:cursor-progress disabled:opacity-70"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            {busy ? 'Planning…' : 'Plan route'}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs text-fd-muted-foreground">Try</span>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              disabled={busy}
              onClick={() => void run(p.start, p.finish)}
              className="rounded-full border px-2.5 py-1 text-xs text-fd-muted-foreground transition-colors hover:border-fd-primary/50 hover:bg-brand-soft hover:text-fd-foreground disabled:opacity-50"
            >
              {p.label}
            </button>
          ))}
        </div>
      </form>

      {state.phase !== 'idle' && <RequestLine state={state} />}

      {state.phase === 'idle' && (
        <div className="grid place-items-center rounded-2xl border border-dashed px-6 py-14 text-center">
          <p className="max-w-sm text-sm text-fd-muted-foreground">
            Pick a trip above, or type any two US places as <code className="font-mono text-fd-foreground">City, ST</code> or{' '}
            <code className="font-mono text-fd-foreground">lat,lon</code>. The request goes to this site&rsquo;s{' '}
            <code className="font-mono text-fd-foreground">/api/route/</code>.
          </p>
        </div>
      )}

      {state.phase === 'loading' && <Skeleton />}
      {state.phase === 'error' && <ErrorPanel problem={state.problem} />}
      {state.phase === 'done' && (
        <Result plan={state.plan} ms={state.ms} dark={dark} focus={focus} onFocus={(i) => setFocus({ i, at: Date.now() })} />
      )}
    </div>
  );
}

function Field({
  icon,
  label,
  value,
  onChange,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="group flex h-12 flex-1 items-center gap-2.5 rounded-xl border bg-fd-background px-3 transition-colors focus-within:border-fd-primary/60 focus-within:ring-2 focus-within:ring-fd-primary/20">
      <span className="text-fd-muted-foreground group-focus-within:text-fd-primary">{icon}</span>
      <span className="sr-only">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label === 'Start' ? 'Dallas, TX' : 'Chicago, IL'}
        autoComplete="off"
        spellCheck={false}
        className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-fd-muted-foreground/70"
      />
      <span className="hidden text-[11px] uppercase tracking-wider text-fd-muted-foreground/80 lg:inline">{label}</span>
    </label>
  );
}

function RequestLine({ state }: { state: Exclude<State, { phase: 'idle' }> }) {
  const status = state.phase === 'done' ? state.status : state.phase === 'error' ? state.problem.status : undefined;
  const ok = state.phase === 'done';
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border bg-fd-muted/60 px-3 py-2 font-mono text-xs">
      <span className="font-semibold text-ok">GET</span>
      <span className="min-w-0 flex-1 truncate text-fd-muted-foreground" title={decodeURIComponent(state.url)}>
        {decodeURIComponent(state.url).replaceAll('+', ' ')}
      </span>
      {state.phase === 'loading' ? (
        <span className="text-fd-muted-foreground">pending…</span>
      ) : (
        <>
          <span className={ok ? 'text-ok' : 'text-bad'}>{status ?? 'network error'}</span>
          <span className="tabular text-fd-muted-foreground">{n0.format(state.ms)} ms</span>
        </>
      )}
    </div>
  );
}

function Result({
  plan,
  ms,
  dark,
  focus,
  onFocus,
}: {
  plan: RoutePlan;
  ms: number;
  dark: boolean;
  focus: { i: number; at: number } | null;
  onFocus: (i: number) => void;
}) {
  const stops = plan.fuel_stops;
  const cached = plan.external_api_calls === 0;
  return (
    <div className="flex flex-col gap-4 animate-fd-fade-in">
      <div className="overflow-hidden rounded-2xl border bg-fd-card">
        <div className="grid grid-cols-2 gap-px bg-fd-border sm:grid-cols-5 [&>*]:bg-fd-card">
          <Stat label="Fuel cost" value={usd.format(plan.total_fuel_cost)} accent hint="bought at stops, full tank at start" wide />
          <Stat label="Distance" value={`${n0.format(plan.distance_miles)} mi`} />
          <Stat label="Drive time" value={hours(plan.duration_hours)} />
          <Stat label="Gallons bought" value={n1.format(plan.total_gallons_purchased)} />
          <Stat label="Fuel stops" value={String(stops.length)} />
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t bg-fd-muted/40 px-4 py-2.5 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-medium ${
              cached ? 'bg-ok/12 text-ok' : 'bg-brand-soft text-fd-primary'
            }`}
          >
            <Zap className="size-3" />
            {cached ? '0 external calls · cache hit' : `${plan.external_api_calls} external call${plan.external_api_calls === 1 ? '' : 's'}`}
          </span>
          <span className="rounded-full border px-2 py-0.5 font-mono tabular text-fd-muted-foreground">
            {n0.format(ms)} ms round trip
          </span>
          <span className="text-fd-muted-foreground">
            Fuel burned over the trip: <span className="tabular text-fd-foreground">{usd.format(plan.cost_of_fuel_consumed)}</span>
          </span>
          <a
            href={plan.map_url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-fd-muted-foreground transition-colors hover:text-fd-primary"
          >
            map_url <ExternalLink className="size-3" />
          </a>
        </div>
      </div>

      <div className="relative h-[440px] overflow-hidden rounded-2xl border bg-fd-muted">
        <RouteMap key={dark ? 'dark' : 'light'} plan={plan} dark={dark} focus={focus} />
      </div>

      {stops.length === 0 ? (
        <div className="rounded-2xl border px-4 py-4 text-sm text-fd-muted-foreground">
          No stops needed: {n0.format(plan.distance_miles)} miles fits in one 500-mile tank. The trip burns{' '}
          {n1.format(plan.distance_miles / 10)} gallons, worth {usd.format(plan.cost_of_fuel_consumed)} at the cheapest corridor price.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-fd-muted/60 text-left text-xs text-fd-muted-foreground">
              <tr className="[&>th]:px-3 [&>th]:py-2.5 [&>th]:font-medium">
                <th className="w-10">#</th>
                <th className="text-right">Mile</th>
                <th>Station</th>
                <th>City</th>
                <th className="text-right">$/gal</th>
                <th className="text-right">Gallons</th>
                <th className="text-right">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {stops.map((s, i) => (
                <tr
                  key={`${s.mile}-${s.name}`}
                  onClick={() => onFocus(i)}
                  className={`cursor-pointer transition-colors hover:bg-brand-soft [&>td]:px-3 [&>td]:py-2.5 ${
                    focus?.i === i ? 'bg-brand-soft' : ''
                  }`}
                >
                  <td>
                    <span className="grid size-5 place-items-center rounded-full bg-brand font-mono text-[10px] font-bold text-fd-primary-foreground">
                      {i + 1}
                    </span>
                  </td>
                  <td className="text-right tabular text-fd-muted-foreground">{n1.format(s.mile)}</td>
                  <td className="max-w-[240px] truncate font-medium" title={`${s.name} · ${s.address}`}>
                    {s.name}
                  </td>
                  <td className="whitespace-nowrap text-fd-muted-foreground">
                    {s.city}, {s.state}
                  </td>
                  <td className="text-right tabular">{s.price.toFixed(3)}</td>
                  <td className="text-right tabular">{n1.format(s.gallons)}</td>
                  <td className="text-right tabular font-semibold">{usd.format(s.cost)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t bg-fd-muted/40 text-sm tabular">
              <tr className="[&>td]:px-3 [&>td]:py-2.5">
                <td colSpan={5} className="font-sans text-xs text-fd-muted-foreground">
                  Click a row to find it on the map
                </td>
                <td className="text-right">{n1.format(plan.total_gallons_purchased)}</td>
                <td className="text-right font-semibold text-fd-primary">{usd.format(plan.total_fuel_cost)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <details className="group rounded-2xl border bg-fd-card [&_summary::-webkit-details-marker]:hidden">
        <summary className="flex cursor-pointer select-none items-center gap-2 px-4 py-3 text-sm font-medium">
          <ArrowRight className="size-3.5 text-fd-muted-foreground transition-transform group-open:rotate-90" />
          Raw response
          <span className="ml-auto font-mono text-xs text-fd-muted-foreground">
            {plan.route.coordinates.length.toLocaleString('en-US')} route points
          </span>
        </summary>
        <pre className="max-h-[420px] overflow-auto border-t px-4 py-3 font-mono text-xs leading-relaxed">
          {JSON.stringify(
            { ...plan, route: { ...plan.route, coordinates: [...plan.route.coordinates.slice(0, 3), `… ${plan.route.coordinates.length - 3} more`] } },
            null,
            2,
          )}
        </pre>
      </details>
    </div>
  );
}

function Stat({ label, value, accent, hint, wide }: { label: string; value: string; accent?: boolean; hint?: string; wide?: boolean }) {
  return (
    <div className={`px-4 py-3.5 ${wide ? 'max-sm:col-span-2' : ''}`} title={hint}>
      <div className="text-xs text-fd-muted-foreground">{label}</div>
      <div
        className={`mt-1 text-2xl font-semibold tabular tracking-tight ${accent ? 'text-fd-primary' : 'text-fd-foreground'}`}
      >
        {value}
      </div>
    </div>
  );
}

function Skeleton() {
  const bar = 'animate-pulse rounded-md bg-fd-muted';
  return (
    <div className="flex flex-col gap-4" aria-busy aria-label="Planning route">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border sm:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="flex flex-col gap-2 px-4 py-3.5">
            <div className={`${bar} h-3 w-16`} />
            <div className={`${bar} h-6 w-24`} />
          </div>
        ))}
      </div>
      <div className="relative grid h-[440px] place-items-center overflow-hidden rounded-2xl border bg-fd-muted/60">
        <RouteSketch />
      </div>
      <div className="flex flex-col gap-2 rounded-2xl border p-3">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className={`${bar} h-5`} style={{ width: `${92 - i * 9}%` }} />
        ))}
      </div>
    </div>
  );
}

/** Loading state: a route line drawing itself across the map area. */
function RouteSketch() {
  return (
    <div className="flex flex-col items-center gap-3 text-fd-muted-foreground">
      <svg viewBox="0 0 240 60" className="w-60" aria-hidden>
        <path
          d="M8 48 C 60 48, 50 14, 110 18 S 170 50, 232 12"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.25"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <path
          d="M8 48 C 60 48, 50 14, 110 18 S 170 50, 232 12"
          fill="none"
          stroke="var(--color-brand)"
          strokeWidth="3"
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray="1"
          style={{ ['--len' as string]: 1, animation: 'route-draw 1.4s cubic-bezier(0.22,1,0.36,1) infinite' }}
        />
      </svg>
      <span className="text-xs">Routing with OSRM, then optimizing stops…</span>
    </div>
  );
}

const PROBLEMS: Record<Problem['kind'], { icon: ReactNode; title: string; help: ReactNode }> = {
  'bad-input': {
    icon: <SearchX className="size-5" />,
    title: 'That location didn’t resolve',
    help: (
      <>
        Use <code>City, ST</code> (e.g. <code>Tulsa, OK</code>) or <code>lat,lon</code>. Places outside the US are rejected.
      </>
    ),
  },
  unreachable: {
    icon: <RouteOff className="size-5" />,
    title: 'No station within range',
    help: <>Some stretch of this route has no station within the 500-mile tank range, so no plan can finish it.</>,
  },
  upstream: {
    icon: <ServerCrash className="size-5" />,
    title: 'The routing provider failed',
    help: <>The public OSRM server is best-effort and rate-limited to 1 request per second. Wait a moment and retry.</>,
  },
  offline: {
    icon: <CloudOff className="size-5" />,
    title: 'The API isn’t running',
    help: (
      <>
        Nothing usable answered behind <code>/api</code>. Start Django with{' '}
        <code>cd api &amp;&amp; uv run python manage.py runserver</code>, or point <code>API_ORIGIN</code> at a running
        instance.
      </>
    ),
  },
  unknown: {
    icon: <ServerCrash className="size-5" />,
    title: 'Unexpected response',
    help: <>The API answered with something this page doesn&rsquo;t recognise. Check the Django logs.</>,
  },
};

function ErrorPanel({ problem }: { problem: Problem }) {
  const p = PROBLEMS[problem.kind];
  return (
    <div role="alert" className="flex gap-3 rounded-2xl border border-bad/30 bg-bad/6 px-4 py-4 animate-fd-fade-in">
      <span className="mt-0.5 text-bad">{p.icon}</span>
      <div className="min-w-0 text-sm [&_code]:rounded [&_code]:border [&_code]:bg-fd-background [&_code]:px-1 [&_code]:font-mono [&_code]:text-[0.85em]">
        <div className="font-semibold">
          {p.title}
          {problem.status ? <span className="ml-2 font-mono text-xs font-normal text-fd-muted-foreground">HTTP {problem.status}</span> : null}
        </div>
        {problem.body?.detail && <p className="mt-1 text-fd-foreground/90">{problem.body.detail}</p>}
        <p className="mt-1 text-fd-muted-foreground">{p.help}</p>
        {problem.body?.error && (
          <p className="mt-2 font-mono text-xs text-fd-muted-foreground">
            error: <span className="text-fd-foreground">{problem.body.error}</span>
          </p>
        )}
      </div>
    </div>
  );
}


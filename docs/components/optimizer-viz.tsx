'use client';
import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, RotateCcw, Shuffle } from 'lucide-react';

const RANGE = 500;
const MPG = 10;
const TOTAL = 1100;

type Station = { name: string; mile: number; price: number };

const DEFAULT: Station[] = [
  { name: 'A', mile: 120, price: 3.4 },
  { name: 'B', mile: 300, price: 3.05 },
  { name: 'C', mile: 460, price: 3.6 },
  { name: 'D', mile: 610, price: 2.95 },
  { name: 'E', mile: 800, price: 3.3 },
  { name: 'F', mile: 960, price: 3.5 },
];

type Step = {
  at: number; // station index, -1 = start
  pos: number;
  fuelIn: number; // miles of fuel on arrival
  buy: number; // miles of fuel bought here
  next: number; // index into stations, stations.length = finish
  text: string;
};

/** Same rule as api/routing/optimizer.py, on miles of fuel instead of gallons. */
export function planStops(stations: Station[], total = TOTAL, range = RANGE): Step[] {
  const pts = [...stations, { name: 'Finish', mile: total, price: 0 }];
  const steps: Step[] = [];
  let at = -1;
  let pos = 0;
  let fuel = range;
  while (at < stations.length) {
    const price = at < 0 ? Infinity : pts[at].price;
    const window = pts.map((p, i) => ({ ...p, i })).filter((p) => p.i > at && p.mile <= pos + range);
    if (!window.length) throw new Error('unreachable');
    const cheaper = window.find((p) => p.price < price);
    let buy: number;
    let next: (typeof window)[number];
    let text: string;
    if (at < 0) {
      next = window[0];
      buy = 0;
      text = `Start with a full tank (${range} mi). Nothing to buy here; drive to ${next.name}.`;
    } else if (cheaper) {
      next = cheaper;
      buy = Math.max(0, cheaper.mile - pos - fuel);
      const target = cheaper.i === stations.length ? 'the finish' : `${cheaper.name} ($${cheaper.price.toFixed(2)})`;
      text = buy
        ? `${cheaper.i === stations.length ? 'The finish' : 'Cheaper fuel at ' + target} is within ${range} mi. Buy just enough to get there: ${(buy / MPG).toFixed(1)} gal.`
        : `${target} is cheaper and already reachable on the fuel in the tank. Buy nothing.`;
    } else {
      buy = range - fuel;
      next = window.reduce((a, b) => (b.price < a.price ? b : a));
      text = `Nothing cheaper within ${range} mi. Fill up here (${(buy / MPG).toFixed(1)} gal) and go to the cheapest station in range, ${next.name}.`;
    }
    steps.push({ at, pos, fuelIn: fuel, buy, next: next.i, text });
    fuel = fuel + buy - (next.mile - pos);
    pos = next.mile;
    at = next.i;
  }
  return steps;
}

const W = 720;
const PAD = 28;
const x = (mile: number) => PAD + (mile / TOTAL) * (W - PAD * 2);

export function OptimizerViz() {
  const [stations, setStations] = useState(DEFAULT);
  const [step, setStep] = useState(0);
  const steps = useMemo(() => planStops(stations), [stations]);
  const cur = steps[Math.min(step, steps.length - 1)];
  const done = step >= steps.length;

  const bought = steps.slice(0, done ? steps.length : step + 1).filter((s) => s.buy > 0);
  const cost = bought.reduce((sum, s) => sum + (s.buy / MPG) * stations[s.at].price, 0);
  const gallons = bought.reduce((sum, s) => sum + s.buy / MPG, 0);

  // fuel level polyline: y = 0 (empty) .. 500 (full)
  const fy = (f: number) => 196 - (f / RANGE) * 70;
  let pts = '';
  for (const s of steps.slice(0, done ? steps.length : step + 1)) {
    const nextMile = s.next === stations.length ? TOTAL : stations[s.next].mile;
    const after = s.fuelIn + s.buy;
    pts += `${x(s.pos)},${fy(s.fuelIn)} ${x(s.pos)},${fy(after)} `;
    if (done || s !== cur) pts += `${x(nextMile)},${fy(after - (nextMile - s.pos))} `;
  }

  function shuffle() {
    setStations((st) => st.map((s) => ({ ...s, price: Math.round((2.8 + Math.random() * 0.9) * 100) / 100 })));
    setStep(0);
  }

  return (
    <div className="not-prose my-6 overflow-hidden rounded-2xl border bg-fd-card">
      <div className="overflow-x-auto px-2 pt-4">
        <svg viewBox={`0 0 ${W} 230`} className="min-w-[560px] w-full text-fd-foreground" role="img" aria-label="Fuel plan along a 1,100 mile route">
          {!done && (
            <rect
              x={x(cur.pos)}
              y={16}
              width={x(Math.min(TOTAL, cur.pos + RANGE)) - x(cur.pos)}
              height={84}
              rx={6}
              fill="var(--color-brand-soft)"
              className="transition-all duration-500"
            />
          )}
          {!done && (
            <text x={x(cur.pos) + 6} y={30} fontSize="10.5" fill="var(--color-brand)" fontFamily="var(--font-mono)">
              next {RANGE} mi
            </text>
          )}
          <line x1={x(0)} x2={x(TOTAL)} y1={70} y2={70} stroke="currentColor" strokeOpacity="0.3" strokeWidth="2" />
          {[
            [0, 'Start'],
            [TOTAL, 'Finish'],
          ].map(([m, label]) => (
            <g key={label}>
              <rect x={x(m as number) - 5} y={65} width={10} height={10} rx={2} fill="currentColor" />
              <text x={x(m as number)} y={92} fontSize="11" textAnchor="middle" fill="var(--color-fd-muted-foreground)">
                {label}
              </text>
            </g>
          ))}
          {stations.map((s, i) => {
            const active = !done && cur.at === i;
            const target = !done && cur.next === i;
            const boughtHere = steps.some((st, k) => st.at === i && st.buy > 0 && (done || k <= step));
            return (
              <g key={s.name} className="transition-opacity" opacity={done || active || target || boughtHere ? 1 : 0.6}>
                <text x={x(s.mile)} y={52} fontSize="11.5" textAnchor="middle" fontFamily="var(--font-mono)" fill="currentColor" fontWeight={active ? 700 : 400}>
                  ${s.price.toFixed(2)}
                </text>
                <circle
                  cx={x(s.mile)}
                  cy={70}
                  r={active ? 8 : 6}
                  fill={boughtHere ? 'var(--color-brand)' : 'var(--color-fd-card)'}
                  stroke={active || target || boughtHere ? 'var(--color-brand)' : 'currentColor'}
                  strokeWidth={target ? 2.5 : 1.5}
                  strokeDasharray={target && !active ? '3 2' : undefined}
                />
                <text x={x(s.mile)} y={92} fontSize="11" textAnchor="middle" fill="var(--color-fd-muted-foreground)">
                  {s.name} · {s.mile}
                </text>
              </g>
            );
          })}

          <text x={PAD} y={120} fontSize="10.5" fill="var(--color-fd-muted-foreground)" fontFamily="var(--font-mono)">
            fuel in tank
          </text>
          <line x1={x(0)} x2={x(TOTAL)} y1={fy(0)} y2={fy(0)} stroke="currentColor" strokeOpacity="0.15" />
          <line x1={x(0)} x2={x(TOTAL)} y1={fy(RANGE)} y2={fy(RANGE)} stroke="currentColor" strokeOpacity="0.15" strokeDasharray="2 3" />
          <text x={x(TOTAL) + 4} y={fy(RANGE) + 3} fontSize="9.5" fill="var(--color-fd-muted-foreground)">
            full
          </text>
          <text x={x(TOTAL) + 4} y={fy(0) + 3} fontSize="9.5" fill="var(--color-fd-muted-foreground)">
            0
          </text>
          <polyline points={pts} fill="none" stroke="var(--color-brand)" strokeWidth="2" strokeLinejoin="round" />
        </svg>
      </div>

      <div className="flex flex-col gap-3 border-t px-4 py-3.5 sm:flex-row sm:items-center">
        <p className="min-h-[2.5em] flex-1 text-sm leading-snug" aria-live="polite">
          {done ? (
            <>
              Arrived. Bought <b className="tabular">{gallons.toFixed(1)} gal</b> for{' '}
              <b className="tabular text-fd-primary">${cost.toFixed(2)}</b>. Every gallon came from the cheapest station that could
              still deliver it.
            </>
          ) : (
            <>
              <span className="mr-2 font-mono text-xs text-fd-muted-foreground">
                {step + 1}/{steps.length}
              </span>
              {cur.text}
            </>
          )}
        </p>
        <div className="flex items-center gap-1.5">
          <span className="mr-2 font-mono text-xs tabular text-fd-muted-foreground">${cost.toFixed(2)}</span>
          <IconButton label="Random prices" onClick={shuffle}>
            <Shuffle className="size-4" />
          </IconButton>
          <IconButton label="Reset" onClick={() => setStep(0)} disabled={step === 0}>
            <RotateCcw className="size-4" />
          </IconButton>
          <IconButton label="Previous step" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
            <ChevronLeft className="size-4" />
          </IconButton>
          <button
            type="button"
            onClick={() => setStep((s) => Math.min(steps.length, s + 1))}
            disabled={done}
            className="inline-flex h-8 items-center gap-1 rounded-lg bg-fd-primary pl-3 pr-2 text-sm font-semibold text-fd-primary-foreground transition hover:brightness-110 disabled:opacity-40"
          >
            Next <ChevronRight className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function IconButton({ label, children, ...rest }: { label: string; children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="grid size-8 place-items-center rounded-lg border text-fd-muted-foreground transition-colors hover:bg-fd-accent hover:text-fd-foreground disabled:opacity-40"
      {...rest}
    >
      {children}
    </button>
  );
}

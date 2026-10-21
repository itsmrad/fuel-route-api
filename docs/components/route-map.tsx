'use client';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useRef } from 'react';
import type { Map as MLMap, Marker } from 'maplibre-gl';
import type { RoutePlan } from './route-types';

const STYLE = {
  dark: 'https://tiles.openfreemap.org/styles/dark',
  light: 'https://tiles.openfreemap.org/styles/positron',
};

const fmt$ = (n: number) => `$${n.toFixed(2)}`;

function el(className: string, text = '') {
  const d = document.createElement('div');
  d.className = className;
  d.textContent = text;
  return d;
}

function popupHtml(i: number, s: RoutePlan['fuel_stops'][number]) {
  const esc = (t: string) => t.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
  return `<div style="min-width:190px">
    <div style="font-size:11px;opacity:.65;font-family:var(--font-mono)">STOP ${i + 1} · MILE ${s.mile.toFixed(1)}</div>
    <div style="font-weight:600;margin-top:2px">${esc(s.name)}</div>
    <div style="opacity:.7;font-size:12px">${esc(s.city)}, ${esc(s.state)}</div>
    <div style="display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin-top:8px;font-size:12px;font-family:var(--font-mono)">
      <span style="opacity:.65">price</span><span>$${s.price.toFixed(3)}/gal</span>
      <span style="opacity:.65">gallons</span><span>${s.gallons.toFixed(1)}</span>
      <span style="opacity:.65">cost</span><span style="color:var(--color-brand);font-weight:600">${fmt$(s.cost)}</span>
    </div></div>`;
}

export default function RouteMap({
  plan,
  dark,
  focus,
}: {
  plan: RoutePlan;
  dark: boolean;
  /** stop index to fly to; `at` makes repeat clicks on the same row re-fire */
  focus: { i: number; at: number } | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<Marker[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ml = await import('maplibre-gl');
      if (cancelled || !box.current) return;
      // The bundler can't follow maplibre's worker import; `npm run dev/build` copies it to public/.
      ml.setWorkerUrl(`/maplibre-gl-worker.mjs?v=${ml.getVersion()}`);
      const coords = plan.route.coordinates;
      const bounds = coords.reduce(
        (b, c) => b.extend(c as [number, number]),
        new ml.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]),
      );
      const m = new ml.Map({
        container: box.current,
        style: dark ? STYLE.dark : STYLE.light,
        bounds,
        fitBoundsOptions: { padding: 48 },
        attributionControl: { compact: true },
        cooperativeGestures: true,
      });
      map.current = m;
      m.addControl(new ml.NavigationControl({ showCompass: false }), 'top-right');
      // The OpenFreeMap styles reference a few icons their sprite lacks; a blank stand-in keeps the console clean.
      m.setMissingStyleImageResolver((id) => {
        m.addImage(id, { width: 1, height: 1, data: new Uint8Array(4) });
      });

      m.on('load', () => {
        // Draw the route above every road but under the labels that follow them, so city names stay readable.
        const layers = m.getStyle().layers;
        const labels = layers.slice(layers.findLastIndex((l) => l.type === 'line') + 1).find((l) => l.type === 'symbol')?.id;
        m.addSource('route', {
          type: 'geojson',
          data: { type: 'Feature', properties: {}, geometry: plan.route },
        });
        m.addLayer({
          id: 'route-casing',
          type: 'line',
          source: 'route',
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: { 'line-color': dark ? '#1a1410' : '#ffffff', 'line-width': 7 },
        }, labels);
        m.addLayer({
          id: 'route',
          type: 'line',
          source: 'route',
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: { 'line-color': dark ? '#f59a4a' : '#c4581a', 'line-width': 3.5 },
        }, labels);
      });

      const ends: [RoutePlan['start'], string][] = [
        [plan.start, 'A'],
        [plan.finish, 'B'],
      ];
      for (const [loc, label] of ends) {
        const node = el(
          'grid size-6 place-items-center rounded-full border-2 border-fd-foreground bg-fd-background font-mono text-[11px] font-bold text-fd-foreground shadow-md',
          label,
        );
        new ml.Marker({ element: node }).setLngLat([loc.lon, loc.lat]).addTo(m);
      }

      markers.current = plan.fuel_stops.map((s, i) => {
        const node = el(
          'grid size-6 cursor-pointer place-items-center rounded-full bg-brand font-mono text-[11px] font-bold text-fd-primary-foreground shadow-[0_2px_6px_rgb(0_0_0/0.35)] ring-2 ring-fd-background transition-transform hover:scale-115',
          String(i + 1),
        );
        node.setAttribute('aria-label', `Stop ${i + 1}: ${s.name}`);
        return new ml.Marker({ element: node })
          .setLngLat([s.lon, s.lat])
          .setPopup(new ml.Popup({ offset: 16, maxWidth: '260px' }).setHTML(popupHtml(i, s)))
          .addTo(m);
      });
    })();
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      markers.current = [];
    };
  }, [plan, dark]);

  useEffect(() => {
    const m = map.current;
    const mk = focus ? markers.current[focus.i] : undefined;
    if (!m || !mk) return;
    markers.current.forEach((x) => x.getPopup()?.isOpen() && x.togglePopup());
    m.flyTo({ center: mk.getLngLat(), zoom: Math.max(m.getZoom(), 7), duration: 900 });
    mk.togglePopup();
  }, [focus]);

  return <div ref={box} className="size-full" />;
}

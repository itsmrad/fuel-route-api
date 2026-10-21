import { Logo } from './logo';

export function ProjectCard() {
  return (
    <div className="rounded-xl border bg-fd-card px-3.5 py-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Logo className="size-4 text-fd-foreground" />
        Fuel Route API
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 font-mono text-xs text-fd-muted-foreground">
        <span className="size-1.5 rounded-full bg-brand" aria-hidden />
        v1.0 · Django 6.1
      </div>
    </div>
  );
}

import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { DocsBody, DocsPage } from 'fumadocs-ui/layouts/docs/page';
import { source } from '@/lib/source';
import { baseOptions } from '@/lib/layout.shared';
import { ProjectCard } from '@/components/project-card';

export const metadata: Metadata = { title: 'Page not found' };

/** 404 inside the docs shell, so the sidebar and search are still one click away. */
export default function NotFound() {
  return (
    <DocsLayout tree={source.getPageTree()} {...baseOptions()} sidebar={{ banner: <ProjectCard /> }}>
      <DocsPage toc={[]} footer={{ enabled: false }}>
        <DocsBody>
          <div className="not-prose flex flex-col items-start gap-4 py-16">
            <span className="font-mono text-sm text-fd-primary">404</span>
            <h1 className="text-3xl font-bold tracking-tight">No road goes here.</h1>
            <p className="max-w-md text-fd-muted-foreground">
              This page doesn&rsquo;t exist, or it moved. Search with <kbd className="rounded border px-1 font-mono text-xs">⌘K</kbd>,
              or start from the overview.
            </p>
            <div className="mt-2 flex flex-wrap gap-2.5">
              <Link
                href="/docs"
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-fd-primary px-4 text-sm font-semibold text-fd-primary-foreground transition hover:brightness-110"
              >
                Overview <ArrowRight className="size-4" />
              </Link>
              <Link
                href="/docs/route-planner"
                className="inline-flex h-10 items-center rounded-xl border px-4 text-sm font-medium transition-colors hover:bg-fd-accent"
              >
                Route planner
              </Link>
            </div>
          </div>
        </DocsBody>
      </DocsPage>
    </DocsLayout>
  );
}

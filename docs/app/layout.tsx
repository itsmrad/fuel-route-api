import { RootProvider } from 'fumadocs-ui/provider/next';
import type { Metadata } from 'next';
import { Overpass, Overpass_Mono } from 'next/font/google';
import './global.css';

const sans = Overpass({ subsets: ['latin'], variable: '--font-overpass' });
const mono = Overpass_Mono({ subsets: ['latin'], variable: '--font-overpass-mono' });

export const metadata: Metadata = {
  // Absolute OG image URLs; set SITE_URL at build time in production.
  metadataBase: new URL(process.env.SITE_URL || 'http://localhost:3000'),
  title: { template: '%s · Fuel Route API', default: 'Fuel Route API Docs' },
  description: 'Cost-optimal fuel stops along any US driving route.',
  twitter: { card: 'summary_large_image' },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body className="flex flex-col min-h-screen font-sans antialiased">
        <RootProvider theme={{ defaultTheme: 'dark' }} search={{ options: { api: '/search' } }}>
          {children}
        </RootProvider>
      </body>
    </html>
  );
}

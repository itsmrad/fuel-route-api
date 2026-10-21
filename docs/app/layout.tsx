import { RootProvider } from 'fumadocs-ui/provider/next';
import type { Metadata } from 'next';
import { Overpass, Overpass_Mono } from 'next/font/google';
import './global.css';

const sans = Overpass({ subsets: ['latin'], variable: '--font-overpass' });
const mono = Overpass_Mono({ subsets: ['latin'], variable: '--font-overpass-mono' });

export const metadata: Metadata = {
  title: { template: '%s · Fuel Route API', default: 'Fuel Route API Docs' },
  description: 'Cost-optimal fuel stops along any US driving route.',
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

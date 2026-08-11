import type { Metadata } from "next";
import Link from "next/link";

import ThemeToggle from "@/components/ThemeToggle";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: SITE_NAME, template: `%s · ${SITE_NAME}` },
  description: SITE_DESCRIPTION,
  openGraph: { type: "website", siteName: SITE_NAME, url: SITE_URL, title: SITE_NAME, description: SITE_DESCRIPTION },
  twitter: { card: "summary", title: SITE_NAME, description: SITE_DESCRIPTION },
  // Let readers and machines discover the feed from any page.
  alternates: { types: { "application/rss+xml": `${SITE_URL}/feed.xml` } },
};

// Set the display before paint (no flash), honoring a saved choice and defaulting to terminal.
const NO_FLASH = `try{var t=localStorage.getItem('theme');document.documentElement.setAttribute('data-theme',t==='paper'?'paper':'dark-amber');}catch(e){document.documentElement.setAttribute('data-theme','dark-amber');}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body>
        <a className="skip-link" href="#content">Skip to content</a>
        <header className="site-header">
          <div className="shell header-row">
            <Link href="/" className="brand" aria-label="Ohmega Monster home">
              {/* Decorative: the wordmark beside it already names the site, so alt is empty
                  rather than repeating "Ohmega Monster" to a screen reader twice. */}
              <img className="brand-mark" src="/logo-mark.png" alt="" width={512} height={512} />
              <span>OHMEGA</span><span className="brand-separator">/</span><span>MONSTER</span>
            </Link>
            <nav className="site-nav" aria-label="Primary navigation">
              <Link href="/">Index</Link>
              <a href="/feed.xml">RSS</a>
              <ThemeToggle />
            </nav>
          </div>
        </header>
        <main id="content" className="shell">{children}</main>
        <footer className="site-footer">
          <div className="shell footer-row">
            <nav aria-label="Secondary navigation">
              <a href="/feed.xml">RSS</a>
              <a href="/sitemap.xml">Sitemap</a>
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}

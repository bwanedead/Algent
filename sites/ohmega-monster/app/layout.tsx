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

// Set the theme before paint (no flash), honoring a saved choice or the OS preference.
const NO_FLASH = `try{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body>
        <header className="masthead">
          <div className="wrap">
            <Link href="/" className="brand">
              OHMEGA<span className="dot">.</span>MONSTER
            </Link>
            <span style={{ display: "flex", gap: 14, alignItems: "baseline" }}>
              <span className="tagline">reality, with the receipts</span>
              <ThemeToggle />
            </span>
          </div>
        </header>
        <main className="wrap">{children}</main>
        <footer>
          <div className="wrap">
            Ohmega Monster · every claim traceable, every wall disclosed · <a href="/">index</a>
          </div>
        </footer>
      </body>
    </html>
  );
}

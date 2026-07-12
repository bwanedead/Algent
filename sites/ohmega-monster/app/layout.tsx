import type { Metadata } from "next";
import Link from "next/link";

import ThemeToggle from "@/components/ThemeToggle";

import "./globals.css";

export const metadata: Metadata = {
  title: "Ohmega Monster",
  description: "An information-first newsroom. Reality, with the receipts.",
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

import Link from "next/link";

import PageTag from "@/components/PageTag";

import { getMenus, hostOf, menuLabel, type RadarMenu } from "@/lib/radar";

// One menu, plus the way through the archive. Shared by /headlines (newest) and /headlines/[slug].
export default async function HeadlinesView({ menu }: { menu: RadarMenu }) {
  const all = await getMenus();
  const i = all.findIndex((m) => m.slug === menu.slug);
  const newer = i > 0 ? all[i - 1] : null;
  const older = i >= 0 && i < all.length - 1 ? all[i + 1] : null;

  return (
    <article className="radar-page">
      <header className="article-header">
        <p className="ptag-row"><PageTag kind="headlines" detail="Not verified" /></p>
        <h1>Headlines</h1>
        <p className="dek">{menuLabel(menu)}</p>
        {/* Said once, plainly: what this is and how far it has been checked. */}
        <p className="radar-note">
          What crossed the wire, as other outlets reported it — not yet independently verified by
          us. Verified reporting is in the Daily, the Theaters and Articles.
        </p>
      </header>

      <ol className="radar-list">
        {menu.leads.map((l) => (
          <li key={l.n} className="radar-lead">
            <span className="radar-n">{l.n}</span>
            <div>
              <h2>{l.title}</h2>
              {l.thesis ? <p>{l.thesis}</p> : null}
              <p className="radar-meta">
                {l.pillars.join(" · ")}
                {l.sources.length ? (
                  <>
                    {l.pillars.length ? " — " : ""}
                    {l.sources.map((u, k) => (
                      <span key={u}>
                        {k ? ", " : ""}
                        <a href={u} target="_blank" rel="noopener noreferrer">{hostOf(u)}</a>
                      </span>
                    ))}
                  </>
                ) : null}
              </p>
            </div>
          </li>
        ))}
      </ol>

      <nav className="radar-pager" aria-label="Earlier and later headline editions">
        {newer ? <Link href={`/headlines/${newer.slug}`}>← Newer: {menuLabel(newer)}</Link> : <span />}
        {older ? <Link href={`/headlines/${older.slug}`}>Older: {menuLabel(older)} →</Link> : <span />}
      </nav>

      <section className="radar-archive" aria-label="All editions">
        <h2>All editions</h2>
        <ul>
          {all.map((m) => (
            <li key={m.slug}>
              {m.slug === menu.slug ? (
                <strong>{menuLabel(m)}</strong>
              ) : (
                <Link href={`/headlines/${m.slug}`}>{menuLabel(m)}</Link>
              )}
              <span className="radar-count"> — {m.leads.length} headlines</span>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

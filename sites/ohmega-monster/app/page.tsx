import Link from "next/link";

import { getAllMeta } from "@/lib/articles";

// The hub: a dense, wiki/terminal-style index of pieces, newest first.
export default function Home() {
  const articles = getAllMeta();
  return (
    <section className="index-page" aria-label="Reports">
      <ul className="feed">
        {articles.length === 0 && (
          <li className="feed-empty">No reports available.</li>
        )}
        {articles.map((a) => (
          <li key={a.slug}>
            <Link href={`/articles/${a.slug}`}>
              <div className="feed-meta">
                <time dateTime={a.date}>{a.date}</time>
                {/* Flags carry the "where" at a glance — derived from the piece's own entities,
                    so they're always literally true (and absent when nothing maps cleanly). */}
                {a.flags.length > 0 && (
                  <span className="feed-flags" aria-label="Places">{a.flags.join(" ")}</span>
                )}
              </div>
              <div className="feed-story">
                <h2>{a.title}</h2>
                {a.dek ? <p>{a.dek}</p> : null}
                {a.tags.length > 0 && (
                  <ul className="feed-tags" aria-label="Topics">
                    {a.tags.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                )}
              </div>
              {/* The thumbnail is a chart built from this piece's own cited data — never a
                  decorative or generated image. Absent for pieces with no analytic. */}
              {a.thumbnail ? (
                <img className="feed-thumb" src={a.thumbnail} alt="" aria-hidden="true" loading="lazy" />
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

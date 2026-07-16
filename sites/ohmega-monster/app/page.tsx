import Link from "next/link";

import { getAllMeta } from "@/lib/articles";

// The hub: a dense, wiki/terminal-style index of pieces, newest first.
export default function Home() {
  const articles = getAllMeta();
  return (
    <section className="index-page" aria-labelledby="index-title">
      <header className="index-header">
        <div>
          <p className="eyebrow">Newsroom</p>
          <h1 id="index-title">Report index</h1>
        </div>
        <p className="index-count">{articles.length} {articles.length === 1 ? "entry" : "entries"}</p>
      </header>
      <ul className="feed">
        {articles.length === 0 && (
          <li className="feed-empty">No reports available.</li>
        )}
        {articles.map((a) => (
          <li key={a.slug}>
            <Link href={`/articles/${a.slug}`}>
              <div className="feed-meta">
                <time dateTime={a.date}>{a.date}</time>
                {a.status ? <span className="status">{a.status}</span> : null}
              </div>
              <div className="feed-story">
                <h2>{a.title}</h2>
                {a.dek ? <p>{a.dek}</p> : null}
              </div>
              <span className="feed-command" aria-hidden="true">Open</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

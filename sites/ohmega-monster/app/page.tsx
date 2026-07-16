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
              </div>
              <div className="feed-story">
                <h2>{a.title}</h2>
                {a.dek ? <p>{a.dek}</p> : null}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

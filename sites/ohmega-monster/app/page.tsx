import Link from "next/link";

import FlagRow from "@/components/FlagRow";
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
                {/* Visual country association — PNG flags (emoji letters fail on many OSes). */}
                <FlagRow flags={a.flags} places={a.places} />
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
              {/* Picture for the card: the hero when the piece has one (drawn for this
                  purpose, 16:9), otherwise a produced analytic — a chart from the piece's own
                  cited data. Decorative only; the alt is empty because the headline beside it
                  already carries the meaning. */}
              {a.hero || a.thumbnail ? (
                <img
                  className="feed-thumb"
                  src={a.hero || a.thumbnail}
                  alt=""
                  aria-hidden="true"
                  loading="lazy"
                />
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

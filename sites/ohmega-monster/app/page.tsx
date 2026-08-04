import Link from "next/link";

import FlagRow from "@/components/FlagRow";
import ShareButton from "@/components/ShareButton";
import { getAllMeta } from "@/lib/articles";
import { SITE_URL } from "@/lib/site";

// The hub: a dense, wiki/terminal-style index of pieces, newest first.
export default function Home() {
  const articles = getAllMeta();
  return (
    <section className="index-page" aria-label="Reports">
      <ul className="feed">
        {articles.length === 0 && (
          <li className="feed-empty">No reports available.</li>
        )}
        {articles.map((a) => {
          const url = `${SITE_URL}/articles/${a.slug}`;
          return (
            <li key={a.slug} className="feed-item">
              <Link href={`/articles/${a.slug}`} className="feed-link">
                <div className="feed-meta">
                  <time dateTime={a.date}>{a.date}</time>
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
              <ShareButton
                className="feed-share"
                url={url}
                title={a.title}
                dek={a.dek}
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

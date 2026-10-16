import Link from "next/link";

import { assetUrl } from "@/lib/assets";
import type { ArticleMeta } from "@/lib/articles";
import { SITE_URL } from "@/lib/site";

import FlagRow from "./FlagRow";
import ShareButton from "./ShareButton";

// The article list: a dense, wiki-style feed, newest first. Shared by /articles (all) and Home (the latest few).
export default function ArticleFeed({ articles }: { articles: ArticleMeta[] }) {
  return (
    <ul className="feed">
      {articles.length === 0 && <li className="feed-empty">No reports available.</li>}
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
                <img className="feed-thumb" src={assetUrl(a.hero || a.thumbnail)} alt="" aria-hidden="true" loading="lazy" />
              ) : null}
            </Link>
            <ShareButton className="feed-share" url={url} title={a.title} dek={a.dek} />
          </li>
        );
      })}
    </ul>
  );
}

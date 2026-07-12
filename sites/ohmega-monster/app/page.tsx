import Link from "next/link";

import { getAllMeta } from "@/lib/articles";

// The hub: a dense, wiki/terminal-style index of pieces, newest first.
export default function Home() {
  const articles = getAllMeta();
  return (
    <>
      <ul className="feed">
        {articles.length === 0 && (
          <li style={{ color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 13 }}>
            no articles yet — the publish pipeline drops them into content/articles/.
          </li>
        )}
        {articles.map((a) => (
          <li key={a.slug}>
            <Link href={`/articles/${a.slug}`}>
              <div className="meta">
                {a.date}
                {a.status ? <>  ·  <span className="status">{a.status}</span></> : null}
              </div>
              <div className="h">{a.title}</div>
              {a.dek ? <div className="dek">{a.dek}</div> : null}
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { getArticle, getSlugs } from "@/lib/articles";

export function generateStaticParams() {
  return getSlugs().map((slug) => ({ slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const a = getArticle(params.slug);
  return a ? { title: `${a.title} · Ohmega Monster`, description: a.dek } : {};
}

export default function ArticlePage({ params }: { params: { slug: string } }) {
  const a = getArticle(params.slug);
  if (!a) notFound();

  return (
    <article>
      <h1>{a.title}</h1>
      {a.dek ? <p className="dek">{a.dek}</p> : null}
      <div className="byline">
        {a.date}
        {a.status ? <>  ·  status: {a.status}</> : null}
      </div>

      <div className="prose">
        <Markdown remarkPlugins={[remarkGfm]}>{a.body}</Markdown>
      </div>

      {a.receipts ? (
        <details className="receipts">
          <summary>▸ How we know this — sources & verification (the receipts)</summary>
          <div className="body">
            <Markdown remarkPlugins={[remarkGfm]}>{a.receipts}</Markdown>
          </div>
        </details>
      ) : null}
    </article>
  );
}

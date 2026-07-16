import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { getArticle, getSlugs } from "@/lib/articles";
import { SITE_URL } from "@/lib/site";

export function generateStaticParams() {
  return getSlugs().map((slug) => ({ slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const a = getArticle(params.slug);
  if (!a) return {};
  const url = `${SITE_URL}/articles/${a.slug}`;
  return {
    title: a.title, // layout template appends " · Ohmega Monster"
    description: a.dek,
    alternates: { canonical: url },
    openGraph: {
      type: "article",
      url,
      title: a.title,
      description: a.dek,
      ...(a.date ? { publishedTime: a.date } : {}),
    },
    twitter: { card: "summary_large_image", title: a.title, description: a.dek },
  };
}

export default function ArticlePage({ params }: { params: { slug: string } }) {
  const a = getArticle(params.slug);
  if (!a) notFound();

  return (
    <article className="article-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">← Index</Link>
      </nav>

      <header className="article-header">
        <h1>{a.title}</h1>
        {a.dek ? <p className="dek">{a.dek}</p> : null}
        <time className="article-date" dateTime={a.date}>{a.date}</time>
      </header>

      <div className="prose">
        <Markdown remarkPlugins={[remarkGfm]}>{a.body}</Markdown>
      </div>

      {a.receipts ? (
        <details className="source-record">
          <summary>
            <span className="disclosure-mark" aria-hidden="true">+</span>
            <span>Source record</span>
            <span className="disclosure-hint">Sources / claims / limits</span>
          </summary>
          <div className="body">
            <Markdown remarkPlugins={[remarkGfm]}>{a.receipts}</Markdown>
          </div>
        </details>
      ) : null}
    </article>
  );
}

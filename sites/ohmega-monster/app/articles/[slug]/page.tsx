import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import FlagRow from "@/components/FlagRow";
import Prose from "@/components/Prose";
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
        <div className="article-meta">
          <time className="article-date" dateTime={a.date}>{a.date}</time>
          <FlagRow flags={a.flags} places={a.places} />
        </div>
      </header>

      <div className="prose">
        <Prose>{a.body}</Prose>
      </div>

      {a.receipts ? (
        <details className="source-record">
          <summary>
            <span className="disclosure-mark" aria-hidden="true">+</span>
            <span>Source record</span>
            <span className="disclosure-hint">Sources / claims / limits</span>
          </summary>
          <div className="body">
            <Prose>{a.receipts}</Prose>
          </div>
        </details>
      ) : null}
    </article>
  );
}

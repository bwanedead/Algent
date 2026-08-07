import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import FlagRow from "@/components/FlagRow";
import Prose from "@/components/Prose";
import ShareButton from "@/components/ShareButton";
import { getArticle, getSlugs } from "@/lib/articles";
import { SITE_URL } from "@/lib/site";

export function generateStaticParams() {
  return getSlugs().map((slug) => ({ slug }));
}

// Soft-publish can ship a piece our editing checks were not satisfied with, and saying so is
// deliberate. But the raw status is PIPELINE vocabulary: a reader met "Review status: needs
// hedging" and learned nothing except that a machine was involved. Same disclosure, said in
// words the reader actually holds. Unknown statuses fall back to a plain generic line rather
// than exposing an internal token.
const REVIEW_NOTICE: Record<string, string> = {
  needs_hedging:
    "Published before our editing checks were satisfied: some claims here may be stated more firmly than the evidence supports.",
  needs_ramp:
    "Published before our editing checks were satisfied: parts of this may be hard to follow without background we did not supply.",
  needs_revision:
    "Published before our editing checks were satisfied: this piece is shorter or thinner than we intend.",
};

function reviewNotice(status: string): string {
  return (
    REVIEW_NOTICE[status] ??
    "Published before our editing checks were satisfied — treat it as a draft."
  );
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
      ...(a.hero ? { images: [`${SITE_URL}${a.hero}`] } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title: a.title,
      description: a.dek,
      ...(a.hero ? { images: [`${SITE_URL}${a.hero}`] } : {}),
    },
  };
}

export default function ArticlePage({ params }: { params: { slug: string } }) {
  const a = getArticle(params.slug);
  if (!a) notFound();
  const qt = a.quickTake;
  const url = `${SITE_URL}/articles/${a.slug}`;

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
          <ShareButton url={url} title={a.title} dek={a.dek} />
        </div>
        {/* Soft-publish can ship non-publishable pieces; the disclosure stays, in plain words. */}
        {a.status && a.status !== "publishable" ? (
          <p className="article-status" role="status">
            {reviewNotice(a.status)}
          </p>
        ) : null}
      </header>

      {qt ? (
        <section className="quick-take" aria-label="At a glance">
          {qt.whatHappened ? (
            <p>
              <span className="quick-take-label">What happened</span>
              {qt.whatHappened}
            </p>
          ) : null}
          {qt.whyItMatters ? (
            <p>
              <span className="quick-take-label">Why it matters</span>
              {qt.whyItMatters}
            </p>
          ) : null}
          {qt.whatIsUncertain ? (
            <p>
              <span className="quick-take-label">Still open</span>
              {qt.whatIsUncertain}
            </p>
          ) : null}
        </section>
      ) : null}

      {a.hero ? (
        <figure className="article-hero">
          {/* Hook text is already burned into the generated image by the hero stage —
              do not overlay it again (that double-captions every hooked hero). heroHook
              stays in frontmatter for feeds/index consumers that want the plain string. */}
          <img src={a.hero} alt={a.heroAlt} />
          {/* The label is not optional furniture: a picture beside a news story is a lie
              unless it says what it is. */}
          <figcaption>{a.heroLabel}</figcaption>
        </figure>
      ) : null}

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

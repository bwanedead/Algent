import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import FlagRow from "@/components/FlagRow";
import Prose from "@/components/Prose";
import ShareButton from "@/components/ShareButton";
import { getArticle, getSlugs } from "@/lib/articles";
import { absoluteAssetUrl, assetUrl } from "@/lib/assets";
import { AI_IMAGE_LABEL, isGeneratedImage, pageHasGeneratedImages } from "@/lib/generated";
import { SITE_URL } from "@/lib/site";
import { intelDoc } from "@/lib/store";

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS; new articles render on demand, no redeploy

export async function generateStaticParams() {
  return (await getSlugs()).map((slug) => ({ slug }));
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

export async function generateMetadata({ params }: { params: { slug: string } }): Promise<Metadata> {
  const a = await getArticle(params.slug);
  if (!a) return {};
  const url = `${SITE_URL}/articles/${a.slug}`;
  // The machine-readable twin (graded claims + sources) for agents — see public/llms.txt.
  const hasTwin = (await intelDoc(`data/articles/${a.slug}.json`)) !== null;
  return {
    title: a.title, // layout template appends " · Ohmega Monster"
    description: a.dek,
    alternates: {
      canonical: url,
      ...(hasTwin
        ? { types: { "application/json": `${SITE_URL}/data/articles/${a.slug}.json` } }
        : {}),
    },
    openGraph: {
      type: "article",
      url,
      title: a.title,
      description: a.dek,
      ...(a.date ? { publishedTime: a.date } : {}),
      ...(a.hero ? { images: [absoluteAssetUrl(a.hero, SITE_URL)] } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title: a.title,
      description: a.dek,
      ...(a.hero ? { images: [absoluteAssetUrl(a.hero, SITE_URL)] } : {}),
    },
  };
}

export default async function ArticlePage({ params }: { params: { slug: string } }) {
  const a = await getArticle(params.slug);
  if (!a) notFound();
  const qt = a.quickTake;
  const url = `${SITE_URL}/articles/${a.slug}`;
  const hasGenerated = pageHasGeneratedImages(a.hero, a.body);

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
        {/* Corrections are visible, never silent. */}
        {a.corrections.map((c) => (
          <p key={c.date + c.note} className="article-correction">
            Updated {c.date}: {c.note}
          </p>
        ))}
        {/* The key, once, at the top — so the frame means something before the reader meets it. */}
        {hasGenerated ? (
          <p className="ai-key">
            <span className="ai-key-swatch" aria-hidden="true" />
            <span>Pictures in this frame are AI-generated, not photographs.</span>
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

      {a.hero && isGeneratedImage(a.hero) ? (
        <figure className="article-hero ai-image">
          {/* Hook text is already burned into the generated image by the hero stage —
              do not overlay it again (that double-captions every hooked hero). heroHook
              stays in frontmatter for feeds/index consumers that want the plain string. */}
          <img src={assetUrl(a.hero)} alt={a.heroAlt} />
          {/* The label is not optional furniture: a picture beside a news story is a lie
              unless it says what it is. */}
          <figcaption className="ai-label">{a.heroLabel || AI_IMAGE_LABEL}</figcaption>
        </figure>
      ) : a.hero ? (
        <figure className="article-hero">
          <img src={assetUrl(a.hero)} alt={a.heroAlt} />
          {/* A real photograph says who took it, under which licence, and where it lives. */}
          <figcaption className="photo-credit">
            {a.heroCredit || "Photo"}
            {a.heroCreditUrl ? (
              <>
                {" · "}
                <a href={a.heroCreditUrl} target="_blank" rel="noopener noreferrer">
                  Wikimedia Commons
                </a>
              </>
            ) : null}
          </figcaption>
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

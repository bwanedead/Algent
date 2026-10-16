import Link from "next/link";

import FlagRow from "@/components/FlagRow";
import Glyph from "@/components/vl/Glyph";
import { assetUrl } from "@/lib/assets";
import type { ArticleMeta } from "@/lib/articles";
import { AI_IMAGE_LABEL, isGeneratedImage } from "@/lib/generated";
import { categoryOf } from "@/lib/visual";

import "./home.css";

// Home's latest articles as picture cards: the article's image, its flags, its title, and nothing else. A generated image keeps its
// signature (cyan frame and an "AI image" tag, the full label as its title/alt text) exactly as on the article page; a card with no
// image shows its category glyph on a tinted field instead of an empty box.

export default function ArticleCards({ articles }: { articles: ArticleMeta[] }) {
  return (
    <ul className="hm-cards">
      {articles.map((a) => {
        const src = a.hero || a.thumbnail;
        const generated = Boolean(a.hero) && isGeneratedImage(a.hero);
        const cat = categoryOf(a.title, a.tags.join(" "));
        return (
          <li key={a.slug}>
            <Link href={`/articles/${a.slug}`} className={`vl-card hm-card vl-cat-${cat}`}>
              <span className={`hm-card-pic${generated ? " is-ai" : ""}`}>
                {src ? (
                  <img src={assetUrl(src)} alt="" aria-hidden="true" loading="lazy" title={generated ? a.heroLabel || AI_IMAGE_LABEL : undefined} />
                ) : (
                  <span className="hm-card-fallback">
                    <Glyph name={cat} size={40} />
                  </span>
                )}
                {generated && <span className="hm-card-ai">AI image</span>}
              </span>
              <span className="hm-card-body">
                <span className="hm-card-meta">
                  <time dateTime={a.date}>{a.date}</time>
                  <FlagRow flags={a.flags} places={a.places} />
                </span>
                <span className="hm-card-title">{a.title}</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

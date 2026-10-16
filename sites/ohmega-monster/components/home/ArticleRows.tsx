import Link from "next/link";

import FlagRow from "@/components/FlagRow";
import Glyph from "@/components/vl/Glyph";
import { assetUrl } from "@/lib/assets";
import type { ArticleMeta } from "@/lib/articles";
import { AI_IMAGE_LABEL, isGeneratedImage } from "@/lib/generated";
import { categoryOf } from "@/lib/visual";

import "./home.css";

// Home's latest articles as thin rows: a small monochrome-treated thumbnail (full colour on hover or focus), date and flags, title.
// A generated image keeps its signature (the cyan hairline frame and an "AI image" tag, the full label as its title) exactly as on
// the article page; a row with no image shows its category glyph in the same square instead of an empty box.

export default function ArticleRows({ articles }: { articles: ArticleMeta[] }) {
  return (
    <ul className="hm-arts">
      {articles.map((a) => {
        const src = a.hero || a.thumbnail;
        const generated = Boolean(a.hero) && isGeneratedImage(a.hero);
        const cat = categoryOf(a.title, a.tags.join(" "));
        return (
          <li key={a.slug}>
            <Link href={`/articles/${a.slug}`} className={`hm-art vl-cat-${cat}`}>
              <span className={`hm-art-pic${generated ? " is-ai" : ""}`} title={generated ? a.heroLabel || AI_IMAGE_LABEL : undefined}>
                {src ? (
                  <img src={assetUrl(src)} alt="" aria-hidden="true" loading="lazy" />
                ) : (
                  <span className="hm-art-fallback">
                    <Glyph name={cat} size={22} />
                  </span>
                )}
                {generated && <span className="hm-art-ai">AI</span>}
              </span>
              <span className="hm-art-body">
                <span className="hm-art-meta">
                  <time dateTime={a.date}>{a.date}</time>
                  <FlagRow flags={a.flags} places={a.places} />
                </span>
                <span className="hm-art-title">{a.title}</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

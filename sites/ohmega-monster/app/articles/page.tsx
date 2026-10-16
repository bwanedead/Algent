import type { Metadata } from "next";

import ArticleFeed from "@/components/ArticleFeed";
import { getAllMeta } from "@/lib/articles";

export const metadata: Metadata = {
  title: "Articles",
  description: "Every article, newest first, with the sources shown.",
  alternates: { canonical: "/articles" },
};

// Every article, newest first. (Home shows only the latest few.)
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function ArticlesPage() {
  const articles = await getAllMeta();
  return (
    <section className="index-page" aria-label="Articles">
      <h1 className="page-title">Articles</h1>
      <ArticleFeed articles={articles} />
    </section>
  );
}

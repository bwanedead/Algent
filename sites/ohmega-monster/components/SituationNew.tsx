"use client";

// NEW: the newest Briefs, daily reports and Pulses, at most five. What is newer than the reader's
// last visit wears the accent; the heading says how many that is.

import Link from "next/link";

import type { ChangeItem } from "@/lib/situation";

import { isNewSince, useSince } from "./SituationVisit";

const KIND = { brief: "Brief", daily: "Daily", pulses: "Pulse" } as const;

export default function SituationNew({ items }: { items: ChangeItem[] }) {
  const since = useSince();
  if (items.length === 0) return null;
  const fresh = items.filter((i) => isNewSince(i.at, since)).length;
  const heading = !since ? "Latest" : fresh > 0 ? `${fresh} new ${since.first ? "this week" : "since your last visit"}` : "Nothing new since your last visit";
  return (
    <section className="sit-sec" aria-labelledby="sit-new-h">
      <div className="sit-head">
        <h2 id="sit-new-h">{heading}</h2>
        <span className="intel-micro">Briefs, daily reports, new Pulses</span>
      </div>
      <ul className="sit-news">
        {items.map((i) => {
          const isNew = isNewSince(i.at, since);
          return (
            <li key={i.key} className={isNew ? "is-new" : undefined}>
              {isNew && <span className="sit-new" role="img" aria-label="New since your last visit" />}
              <time className="intel-micro sit-news-when" dateTime={i.at}>
                {i.whenLabel}
              </time>
              <Link href={i.href} className="sit-news-body">
                <span className="intel-micro sit-news-kind">{KIND[i.kind]}</span>
                <strong>{i.title}</strong>
                {i.detail && <span className="sit-news-detail">{i.detail}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

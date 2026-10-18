"use client";

import { pointsAt, type PanelProps } from "../types";

/** Notable posts of the day. Typed stub: renders the feed when `HudData.tweets` is filled (contract: HudTweet in lib/globe/hud-data.ts)
 *  and says plainly that there is no feed otherwise. Nothing here is invented. */
export default function TweetsPanel({ ctx }: PanelProps) {
  const tweets = ctx.data.tweets;
  if (!tweets) return <p className="hud-none">No feed connected yet. The panel lights up when notable posts of the day are published (see HudTweet in lib/globe/hud-data.ts).</p>;
  if (tweets.length === 0) return <p className="hud-none">No notable posts today.</p>;
  return (
    <ul className="hud-rows">
      {tweets.map((t) => (
        <li key={t.id} className="hud-tweet" {...pointsAt(ctx, t.iso)}>
          <p className="hud-k">{t.author} <a href={t.url} target="_blank" rel="noopener noreferrer">@{t.handle}</a> · {t.at.slice(0, 10)}</p>
          <p className="hud-lede">{t.text}</p>
          {t.why && <p className="hud-cap">{t.why}</p>}
        </li>
      ))}
    </ul>
  );
}

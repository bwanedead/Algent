"use client";

import Link from "next/link";

import { THEMES } from "@/lib/globe/themes";

import { pointsAt, type PanelProps } from "../types";

const themeLabel = (id: string): string => THEMES.find((t) => t.id === id)?.label ?? id;

/** Today's report: its headline, then one line per theater (and the top developments), each with the theme dot the map fill uses. */
export default function DailyPanel({ ctx }: PanelProps) {
  const d = ctx.data.daily;
  if (!d) return <p className="hud-none">No daily report published yet.</p>;
  return (
    <>
      <p className="hud-lede"><span className="hud-k">{d.date}</span> {d.headline}</p>
      <ul className="hud-rows">
        {d.items.map((it, i) => (
          <li key={`${it.href}-${i}`} {...pointsAt(ctx, it.iso)}>
            <Link href={it.href} className="hud-row">
              <span className={`gv-bd gv-th gv-t-${it.theme} gv-r0`} role="img" aria-label={themeLabel(it.theme)} title={themeLabel(it.theme)} />
              <span className="hud-row-text">{it.text}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="hud-foot"><Link href="/geopolitics">Full report</Link></p>
    </>
  );
}

import Link from "next/link";
import type { ReactNode } from "react";

import Popover from "@/components/Popover";
import { linkTarget } from "@/lib/dossier";

// Small shared pieces of the dossier pages. Server components; styled by app/intel/theaters/theaters.css.

/** One dossier section: a claim heading, one lead line that carries the finding, then the picture. */
export function Section({ id, title, lead, children, aside }: { id: string; title: string; lead?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section id={id} className="th-sec" aria-labelledby={`${id}-h`}>
      <div className="th-sec-head">
        <h2 id={`${id}-h`}>{title}</h2>
        {aside}
      </div>
      {lead && <p className="th-lead">{lead}</p>}
      {children}
    </section>
  );
}

/** "Earlier (12) ›": everything past the first screen, one click away, never a reflow. */
export function Overflow({ label, trigger, wide = false, children }: { label: string; trigger: string; wide?: boolean; children: ReactNode }) {
  return (
    <Popover label={label} triggerClassName="th-link-btn" trigger={<>{trigger} ›</>} wide={wide}>
      <div className="geo-pd">
        <p className="geo-pd-title">{label}</p>
        {children}
      </div>
    </Popover>
  );
}

/** A link to an internal path or an external http(s) URL; plain text when the target is not linkable. */
export function Anchor({ url, children, className }: { url: string; children: ReactNode; className?: string }) {
  const t = linkTarget(url);
  if (!t) return <span className={className}>{children}</span>;
  return t.external ? (
    <a href={t.href} className={className} target="_blank" rel="noopener noreferrer nofollow">
      {children} ↗
    </a>
  ) : (
    <Link href={t.href} className={className}>
      {children}
    </Link>
  );
}

/** Solid = researched, hollow = reported (the same quiet pair as the daily report). */
export function VerifyKey() {
  return (
    <span className="th-key">
      <span className="geo-v is-solid" aria-hidden="true" /> researched <span className="geo-v is-hollow" aria-hidden="true" /> reported
    </span>
  );
}

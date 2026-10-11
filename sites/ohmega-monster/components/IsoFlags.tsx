import { countryName, flagImageUrl } from "@/lib/flags";

import "./pulse-tile.css";

/**
 * Flag images for ISO alpha-2 codes (PNG, like FlagRow: emoji flags collapse to letter pairs on many
 * Windows/Linux stacks). Each flag carries its full country name as title and alt ("Saudi Arabia", not
 * "SA"). Renders nothing for an empty list, unless `unknown` is set: then a neutral outlined flag stands
 * in (never an empty gap), titled with that text (the organisation if known, else "Country not specified").
 */
export default function IsoFlags({ codes, className = "isof", unknown }: { codes: string[]; className?: string; unknown?: string }) {
  const list = codes.filter((c) => /^[A-Za-z]{2}$/.test(c));
  if (list.length === 0) {
    if (unknown === undefined) return null;
    const why = unknown.trim() || "Country not specified";
    return (
      <span className={className} title={why} role="img" aria-label={why}>
        <svg className="isof-img isof-unknown" viewBox="0 0 16 12" width={16} height={12} aria-hidden="true" focusable="false">
          <rect x="0.5" y="0.5" width="15" height="11" fill="none" stroke="currentColor" strokeDasharray="2 1.5" />
          <path d="M5.5 4.6c0-1 .9-1.6 2.5-1.6s2.5.6 2.5 1.6c0 1.5-2.5 1.4-2.5 3.2M8 9v.6" fill="none" stroke="currentColor" strokeWidth="0.9" />
        </svg>
      </span>
    );
  }
  return (
    <span className={className} title={list.map(countryName).join(" · ")}>
      {list.map((c, i) => {
        const name = countryName(c);
        return (
          <img key={`${c}-${i}`} className="isof-img" src={flagImageUrl(c, 20)} srcSet={`${flagImageUrl(c, 40)} 2x`} width={16} height={12} alt={name} title={name} loading="eager" decoding="async" />
        );
      })}
    </span>
  );
}

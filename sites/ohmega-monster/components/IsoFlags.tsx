import { flagImageUrl } from "@/lib/flags";

import "./pulse-tile.css";

/**
 * Flag images for ISO alpha-2 codes (PNG, like FlagRow: emoji flags collapse to letter pairs on many
 * Windows/Linux stacks). Decorative beside a title that already names the country, so the images carry
 * an empty alt and the codes are available as a title tooltip. Renders nothing for an empty list.
 */
export default function IsoFlags({ codes, className = "isof" }: { codes: string[]; className?: string }) {
  const list = codes.filter((c) => /^[A-Za-z]{2}$/.test(c));
  if (list.length === 0) return null;
  return (
    <span className={className} title={list.join(" · ")} aria-hidden="true">
      {list.map((c, i) => (
        <img key={`${c}-${i}`} className="isof-img" src={flagImageUrl(c, 20)} srcSet={`${flagImageUrl(c, 40)} 2x`} width={16} height={12} alt="" loading="eager" decoding="async" />
      ))}
    </span>
  );
}

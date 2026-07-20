import { flagEmojiToIso, flagImageUrl } from "@/lib/flags";

type Props = {
  /** Regional-indicator emoji strings from article frontmatter (e.g. "🇦🇺"). */
  flags: string[];
  /** Optional country names aligned with flags (for alt/title). */
  places?: string[];
  className?: string;
};

/**
 * Visual country association for browsing. Prefer PNG flags — emoji regional indicators
 * often render as bare letter pairs (AU, GB) on Windows, which is unreadable as a "flag".
 */
export default function FlagRow({ flags, places = [], className = "feed-flags" }: Props) {
  if (!flags.length) return null;
  return (
    <span className={className} aria-label={places.length ? places.join(", ") : "Places"}>
      {flags.map((flag, i) => {
        const iso = flagEmojiToIso(flag);
        const label = places[i] || iso || "place";
        if (!iso) {
          return (
            <span key={`flag-${i}`} className="feed-flag-fallback" title={label}>
              {flag}
            </span>
          );
        }
        return (
          <img
            key={`flag-${i}-${iso}`}
            className="feed-flag-img"
            src={flagImageUrl(iso, 20)}
            srcSet={`${flagImageUrl(iso, 40)} 2x`}
            width={20}
            height={15}
            alt={label}
            title={label}
            // Eager: the index shows only a few flags per row; lazy load was hiding siblings
            // in tight grid cells on some browsers.
            loading="eager"
            decoding="async"
          />
        );
      })}
    </span>
  );
}

"use client";

import Tip from "@/components/Tip";

// The small "i" that says where a number comes from: basis, source, what is counted, why it is a minimum, and what it is compared with.
// The lines come from lib/stats/render.ts (`statView(...).lines`), never typed at the call site. It reuses the site's Tip bubble.

export default function InfoHover({ label, lines }: { label: string; lines: string[] }) {
  return <Tip corner label={label} text={lines.join("\n")} />;
}

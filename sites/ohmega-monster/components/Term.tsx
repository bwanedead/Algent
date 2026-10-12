import type { ReactNode } from "react";

import { GLOSSARY, type GlossaryId } from "@/lib/glossary";

import Tip from "./Tip";

// A word with its plain-English hint. `id` is a glossary entry (lib/glossary.ts); `text` overrides it for
// an explanation that arrives with the data (the backend's `plain` fields). No text, no mark: the words render
// as they are. A server component, so pages use it freely; only the hint itself is client code.

export default function Term({ id, text, label, children }: { id?: GlossaryId; text?: string; label?: string; children: ReactNode }) {
  const note = (text ?? (id ? GLOSSARY[id] : "")).trim();
  if (!note) return <>{children}</>;
  return (
    <Tip text={note} label={label ?? (typeof children === "string" ? children : (id ?? "this"))}>
      {children}
    </Tip>
  );
}

/** A tile corner "i". Place it as the sibling of the tile button inside a `.tip-host` wrapper. */
export function TipCorner({ text, label }: { text: string; label: string }) {
  return text.trim() ? <Tip text={text} label={label} corner /> : null;
}

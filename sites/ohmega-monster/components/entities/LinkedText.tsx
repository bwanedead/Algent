import Link from "next/link";

import { linkText } from "@/lib/countries";
import { textLinker } from "@/lib/entities";

import "./entities.css";

// Prose with its country names linked to their actor pages. Rendered on the server from the same states the
// entity graph knows (no model call); first mention per string only, dotted underline so it reads as text, not as
// a button. Use it for running text, never inside a heading or an existing link. `skip`: the state the page is about.

export default async function LinkedText({ text, skip = "" }: { text: string; skip?: string }) {
  const parts = linkText(text, await textLinker(), skip);
  return (
    <>
      {parts.map((p, i) =>
        p.iso ? (
          <Link key={i} href={`/intel/actors/${p.iso}`} className="en-inl">
            {p.text}
          </Link>
        ) : (
          p.text
        ),
      )}
    </>
  );
}

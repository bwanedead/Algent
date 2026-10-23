import { updatePending } from "@/lib/contract";

// Shown by a page that has already read its data when a published document was refused because its schema major is newer than this build reads
// (lib/contract.ts): the server moved to a new format before this site caught up. The affected sections show their usual "nothing published" state; this says why.
// Render it AFTER the page's awaits, so it sees what they refused. Server component; renders nothing when everything read was understood.
export default function UpdatePending() {
  const why = updatePending();
  if (why.length === 0) return null;
  return (
    <p className="th-asof" role="status" title={why.join("\n")}>
      Update pending: some data is in a newer format than this page can show yet. It will appear when the site is updated.
    </p>
  );
}

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

// One markdown renderer for the whole site, so article prose and the source record behave
// identically. NOTE: no rehype-raw — raw HTML in content is never rendered, and markdown images
// become <img>, which is what keeps AI-generated SVG analytics from executing anything.
const components = {
  // Outbound links open in a new tab: a reader checking a source (the receipts are *made* of
  // outbound links) should not lose the piece they were reading. Internal/anchor links stay
  // in-tab. rel=noopener/noreferrer is required with target=_blank — without it the opened page
  // gets window.opener access back into ours.
  a({ href, children, ...rest }: { href?: string; children?: React.ReactNode }) {
    const external = !!href && /^https?:\/\//i.test(href);
    return external ? (
      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    ) : (
      <a href={href} {...rest}>
        {children}
      </a>
    );
  },
};

export default function Prose({ children }: { children: string }) {
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </Markdown>
  );
}

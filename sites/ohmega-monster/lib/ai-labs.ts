// One lab, one colour, everywhere on the site. This file is the single source of truth for WHICH colour a lab wears (a fixed slot per known lab, so a
// lab never changes colour when the ranking moves); app/intel/ai/ai.css (components/ai/ai.css) defines the slot colours for both themes. A lab not listed
// here wears a neutral grey and is always labelled by name. Lab ids are the backend's (`ai_benchmarks/labs.py`: slug of the canonical name).

const SLOTS: Record<string, number> = {
  openai: 0,
  anthropic: 1,
  google: 2,
  meta: 3,
  xai: 4,
  deepseek: 5,
  alibaba: 6,
  mistral: 7,
  "z-ai": 8,
  moonshot: 9,
  microsoft: 10,
  nvidia: 11,
  amazon: 12,
  aws: 12,
  bytedance: 13,
};

/** The CSS colour for a lab (a custom property defined per theme in components/ai/ai.css). */
export function labColor(lab: string): string {
  const slot = SLOTS[lab];
  return slot === undefined ? "var(--ai-c-other)" : `var(--ai-c${slot})`;
}

// The data colours of the native map figures (MapStory, NativeFlow): one set per basemap theme, tuned to read on that basemap.
// Client-safe: no imports beyond a type.

import type { Palette } from "./storyFrame";

export const PALETTE: Record<"paper" | "dark", Palette> = {
  paper: { ink: "#1f2933", accent: "#c2410c", warn: "#d98e04", cool: "#1d6fa5", hot: "#c8321e", good: "#2f7a46" },
  dark: { ink: "#e5e7eb", accent: "#f0a33a", warn: "#f0b429", cool: "#5aa9d6", hot: "#ff6b4a", good: "#6fbf7f" },
};

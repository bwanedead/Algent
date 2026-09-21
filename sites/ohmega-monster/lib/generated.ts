// Which pictures on a page were generated rather than photographed.
//
// The pipeline names every generated in-body picture `figure_*` and every hero is generated, so
// this is decided by the file, not by a caption the model wrote. That matters: the signature is
// only honest if it cannot be forgotten.

export function isGeneratedImage(src?: string): boolean {
  if (!src) return false;
  const name = src.split("?")[0].split("/").pop() ?? "";
  return name.startsWith("figure_") || name.startsWith("hero.") || name.startsWith("hero_");
}

export function pageHasGeneratedImages(hero: string, body: string): boolean {
  return Boolean(hero) || /\/figure_[^)\s]+\.(?:jpe?g|png|webp)/i.test(body);
}

export const AI_IMAGE_LABEL = "AI-generated image — not a photograph";

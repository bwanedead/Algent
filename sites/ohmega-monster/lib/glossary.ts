// The site's glossary of desk and interface terms: what a newcomer needs in order to read a label, in plain
// words (what it is + why it matters, at most two sentences). Pure data, safe for server and client code.
//
// The meaning of a MEASURED series (a price, a transit count, a policy rate) is NOT here: the backend
// instrument catalog owns it (`Series.plain` in backend/algent_backend/instruments/catalog.py) and publishes it
// inside each daily record as `tracker.plain` (and `metric.plain` for a state's annual statistics). This file
// holds only what the site itself says. Use it through <Term id="..."> (components/Term.tsx).

export const GLOSSARY = {
  pulse: "A Pulse is a 0 to 100 gauge of how tense one specific situation is, from calm at the bottom to extreme at the top. It is reassessed whenever new evidence arrives, so the number moves with events.",
  band: "The colour band says where a Pulse sits: calm, elevated, severe or critical. Bands are fixed cut-offs on the 0 to 100 scale, so the same colour always means the same level.",
  theater: "A situation is one ongoing story we follow as a unit, such as a war, a standoff, a trade fight or a race between labs, however many places it touches.",
  researched: "We checked this against sources we can cite, beyond what a single outlet said. It still can be wrong, but it has been looked at.",
  reported: "Taken from news outlets and not independently checked by us. Treat it as a lead, not a settled fact.",
  fromHeadlines: "This report was built from news headlines and feeds only; we did not run our own source-by-source research for it.",
  direction: "Whether the situation itself is getting worse (rising), easing, holding steady or unclear compared with the weeks before. It describes events, not how much is written about them.",
  pace: "How fast the situation is changing: fast, gradual or flat.",
  coverage: "How much of the world's news is about this situation compared with a few days ago. More coverage does not mean things are worse, only that more is being written.",
  heat: "A measure of how much news attention a situation is getting right now, relative to everything else. It tracks attention, not danger.",
  chokepoint: "A narrow passage that a large share of world shipping has to squeeze through, such as the Strait of Hormuz or the Suez Canal. Trouble there quickly shows up in oil, gas and goods prices.",
  transits: "The number of ships that passed through a point (a strait or canal) in a day. A sudden drop usually means closure, danger or rerouting.",
  unusual: "This reading is far outside its own normal range (about two standard deviations from its recent history). It means unusual for this measure, not good or bad.",
  flows: "Dated physical readings, such as ships passing a strait or a central bank's rate, as opposed to daily market prices. Each shows the day it is for, because some sources publish with a delay.",
  annual: "Yearly statistics from official sources, each with the year it is for. They show the structure of a country, such as its size, debts and armed forces, not what happened today.",
  onRecord: "What named people or bodies said, in their own words or closely paraphrased, with the source. A statement proves it was said, not that it is true.",
  spotlight: "A story that few outlets were covering, picked from a sweep of the whole world and researched in full.",
  sweep: "A scan of the world's news beyond the situations we follow, to catch stories that deserve attention but have not made the board.",
  keyFigures: "The few numbers that carry the story, each taken from our research or a measured series and shown with its date.",
  baseline: "What the same number was before, or what is normal, so the figure can be read in context.",
  dossier: "The standing file on a situation: background, the actors, the timeline, the Pulses and our outlook, updated as the daily reports accumulate.",
  update: "A later addition to a section already published earlier the same day: it says only what has moved since.",
  outlook: "Our estimate of where this is heading, in probability language such as likely or unlikely, with what it rests on.",
  watch: "Specific things to look for that would show which way the situation is going.",
  sparkline: "A tiny chart of the last year of readings, so you can see at a glance whether today's number is high or low for this series.",
} as const;

export type GlossaryId = keyof typeof GLOSSARY;

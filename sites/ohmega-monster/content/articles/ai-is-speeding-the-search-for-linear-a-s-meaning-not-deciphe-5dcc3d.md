---
title: AI is speeding the search for Linear A’s meaning, not deciphering it
dek: A 2026 proposal that the Bronze Age Cretan script encodes an extinct Semitic language remains unverified, while better software and digital corpora make its claims easier to test.
date: '2026-07-31'
published_at: '2026-07-31T12:37:05.712539+00:00'
as_of: '2026-07-30'
status: publishable
tags:
- science
- Linear A
- Artificial intelligence and machine learning
- Linear B
- Minoan language
places:
- Greece
flags:
- 🇬🇷
hero: /analytics/ai-is-speeding-the-search-for-linear-a-s-meaning-not-deciphe-5dcc3d/hero.jpg
hero_alt: Clay tablets bearing ancient Minoan script
hero_label: AI-generated illustration — not a photograph of this story
hero_hook: Linear A remains undeciphered
---

A Bronze Age writing system from Crete has become much faster to analyze with AI, but it has not thereby become understood. Tom Di Mino, an AI engineer and amateur linguist, announced in June 2026 that he had deciphered Linear A and identified the language behind it as an extinct member of the Semitic family. The claim remains unverified, while the tools that could test it are becoming more accessible.

Linear A was used mainly on Crete and other parts of the Aegean between about 1800 and 1450 BCE by the Minoan civilization. It is a logo-syllabic script: some signs can represent syllables, while others can stand for whole words, quantities or administrative functions. The surviving inscriptions include economic records on clay as well as cultic and utilitarian objects. They are generally short, formulaic, fragmentary or damaged, rather than long passages of prose.

The related script Linear B provides a useful but limited foothold. Linear B was deciphered in 1952 as an early form of Greek. Because some Linear A signs have similar shapes—and may have retained similar sound values—scholars can make approximate phonetic transcriptions of parts of Linear A. That does not transfer Linear B's Greek language or meanings into Linear A. The language written in Linear A remains unidentified, and no language-family affiliation has been demonstrated.

That distinction is central to Di Mino's claim. A decipherment is not simply a list of plausible sounds or recurring sign sequences. It is a demonstrated system connecting signs to sounds, words, grammar and meaning across texts, including material that was not selected to support the original hypothesis.

Di Mino's account began with a proposed reading of a recurring word in sanctuary or libation inscriptions. He linked it to a Semitic root associated with “to dwell” or “to inhabit,” then used programming scripts and language-model-assisted tools to search and cross-reference the Linear A corpus. He reported readings for 40 signs and a lexicon of roughly 400 words; contemporary coverage described the lexicon as containing 408 entries. His public announcement said that the work would next be vetted with academics and linguists, and described the underlying manuscript as a draft rather than a peer-reviewed publication.

The public software trail is real, but it establishes less than the announcement claims. A repository associated with Di Mino is primarily a Claude Code configuration project. A June commit describes a proposed registry of 334 Linear A signs, polyphonic readings, cross-script mappings and searches against 2,871 reconstructed Proto-Semitic roots. It also names tools for building a registry, looking up signs and searching possible cognates.

Those are concrete research artifacts. They are not, by themselves, a reproducible decipherment. The inspected public materials do not include the complete manuscript, full sign-value tables, a fixed corpus snapshot, preprocessing decisions, complete translations, the full lexicon or a submission record. The repository shows how a proposed analysis might be organized; it does not independently establish that the proposed readings are correct. Nor does the absence of those materials prove the claim false. It leaves the claim open to testing.

Linear A is unusually vulnerable to persuasive-looking partial solutions. The surviving record is small—roughly 1,500 inscriptions and about 7,500 characters by some counts, although totals vary—and no bilingual inscription provides an independent equivalent of the Rosetta Stone. A sign's function can change with context: it may act as a syllabogram, a logogram, a transaction sign or a fraction. Word boundaries and readings can also be uncertain. In a repetitive corpus, a flexible hypothesis can find matches without explaining how the language works.

A serious test would therefore have to reach beyond the recurring ritual formula that supplied Di Mino's starting point. It would need to show coherent morphology and syntax, explain administrative as well as cultic texts, account for sign polyphony, logograms, fractions and exceptions, compare the Semitic proposal with alternatives, and make successful predictions on inscriptions withheld from the initial analysis. Independent specialists would need enough data and code to reproduce the result and assess whether it is less ad hoc than competing interpretations.

AI can help with much of that work. Statistical systems can find repeated sequences, rank possible correspondences, compare sign variants, suggest restorations for damaged passages and search a digitized corpus far faster than a person working through printed volumes. Open resources such as SigLA—the Signs of Linear A database—make occurrences, sign positions, variants and document contexts searchable across a corpus that was once primarily available in print.

But pattern detection is not the same as meaning. A model can learn which signs tend to occur together without knowing what those signs refer to. It can rank a proposed correspondence without proving that the language family is right. The distinction resembles the difference between predicting the next word in a text and translating that text: regularity is useful evidence, but it does not supply semantics on its own.

Published computational work shows both the promise and the boundary. A 2019 neural system tested Ugaritic against Hebrew and Linear B against known ancient Greek. It correctly translated 67.3% of cognates in one Linear B benchmark and improved earlier Ugaritic results by five percentage points. Those are meaningful results on defined, externally anchored tasks. They are not decipherment rates for an unknown language with no bilingual text or confirmed relative.

A later model jointly addressed word segmentation and cognate alignment and tested language closeness on Gothic, Ugaritic and Iberian. Its Iberian result—75% precision at 10 in a personal-name experiment—was a limited test with partial external knowledge, not a corpus-wide translation. The authors also noted that their method was demonstrated on alphabetic inputs; Linear A's logo-syllabic system, logograms and uncertain sign functions create a different problem.

The durable change is therefore methodological rather than conclusive. AI lowers the cost of searching and testing hypotheses, while digital corpora make the underlying evidence easier to inspect. Linguists, epigraphers, archaeologists and historians still have to determine whether a proposed reading fits the signs, the chronology, the writing practices, the archaeological context and the full range of texts.

For now, the defensible description is simple: Di Mino has proposed a Semitic decipherment of Linear A, supported by a reported lexicon and a developing software workflow. The public record has not yet shown the reproducible manuscript, independent specialist assessment or corpus-wide predictions needed to change Linear A's scholarly status from undeciphered. AI has made the route to that test faster. It has not removed the need for one.

---
## How we know this

**How this piece is framed:** AI has changed the speed and scale of testing hypotheses about Linear A, but the 2026 claim to have deciphered the script remains an unverified proposal because the problem lacks the external anchors and reproducible evidence that make computational decipherment testable.

**Sources**
- (primary) tdimino/claude-code-minoan — GitHub — https://github.com/tdimino/claude-code-minoan  ·  _read in full · captured 2026-07-31_
- (primary) On automatic decipherment of lost ancient scripts relying on combinatorial optimisation and coupled simulated annealing — Frontiers in Artificial Intelligence — https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1581129/full  ·  _read in full · captured 2026-07-31_
- (primary) SigLA: The signs of Linear A — https://sigla.phis.me/about.html  ·  _read in full · captured 2026-07-31_
- (primary) Linear A — University of Cambridge Research Outputs — https://www.repository.cam.ac.uk/items/f50c0df4-f355-4bc0-be2a-8e960b2bb5da  ·  _read in full · captured 2026-07-31_
- (primary) SigLA: The Signs of Linear A: a palæographical database — https://sigla.phis.me/paper.html  ·  _read in full · captured 2026-07-31_
- (primary) feat(linear-a-decipherment): add unified sign registry with polyphonic readings — GitHub — https://github.com/tdimino/claude-code-minoan/commit/be665998039b838204d87dda0e621904fc96af2f  ·  _read in full · captured 2026-07-31_
- (primary) Deciphering Undersegmented Ancient Scripts Using Phonetic Prior — Transactions of the Association for Computational Linguistics — https://transacl.org/index.php/tacl/article/view/2449  ·  _read in full · captured 2026-07-31_
- (primary) Machine Learning for Ancient Languages: A Survey — Computational Linguistics / MIT Press — https://aclanthology.org/2023.cl-3.5/  ·  _read in full · captured 2026-07-31_
- (primary) Public announcement claiming Linear A decipherment — LinkedIn — https://www.linkedin.com/posts/tomdimino_without-too-much-ballyhoo-im-honored-and-activity-7471395019157835776-ETxU  ·  _read in full · captured 2026-07-31_
- (primary) Neural Decipherment via Minimum-Cost Flow: From Ugaritic to Linear B — Association for Computational Linguistics — https://aclanthology.org/P19-1303.pdf  ·  _read in full · captured 2026-07-31_
- (primary) DecipherUnsegmented — GitHub — https://github.com/j-luo93/DecipherUnsegmented/  ·  _read in full · captured 2026-07-31_
- (primary) Neural Decipherment via Minimum-Cost Flow: From Ugaritic to Linear B — Association for Computational Linguistics — https://aclanthology.org/P19-1303/  ·  _read in full · captured 2026-07-31_
- (primary) Deciphering Undersegmented Ancient Scripts Using Phonetic Prior — MIT Press / Transactions of the Association for Computational Linguistics — https://aclanthology.org/2021.tacl-1.5.pdf  ·  _read in full · captured 2026-07-31_
- (primary) NeuroDecipher — GitHub — https://github.com/j-luo93/NeuroDecipher  ·  _read in full · captured 2026-07-31_
- (secondary) AI Engineer Claims to Have Cracked Linear A — AI Clambake — https://aiclambake.com/clamtakes/linear-a/  ·  _read in full · captured 2026-07-31_
- (secondary) Cracking the code: can AI help us decipher ancient languages? — The Conversation — https://theconversation.com/cracking-the-code-can-ai-help-us-decipher-ancient-languages-288238  ·  _read in full · captured 2026-07-31_
- (secondary) What happens when you put AI to work deciphering lost languages? — Ars Technica — https://arstechnica.com/science/2026/07/what-happens-when-you-put-ai-to-work-deciphering-lost-languages/  ·  _read in full · captured 2026-07-31_
- (secondary) Translating lost languages using machine learning — MIT News — https://news.mit.edu/2020/translating-lost-languages-using-machine-learning-1021  ·  _read in full · captured 2026-07-31_

**Claims, and how far we tracked each down**
- _[confirmed]_ Linear A is a Bronze Age logo-syllabic writing system used primarily on Crete between roughly 1800 and 1450 BCE.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Linear B was deciphered as an early form of Greek, while the language represented by Linear A remains unidentified.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Linear A shares substantial graphic and probable phonetic continuities with Linear B, allowing approximate sound values to be assigned to many Linear A signs without understanding the underlying language.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Linear A was used in administrative and non-administrative contexts, including economic records, cultic objects, vessels, stone objects, and metal objects.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Linear A has not been demonstrably affiliated with a known language family.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Statistical pattern matching can identify recurring sequences, test sign or word hypotheses, and assist with damaged-text restoration.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ A model can learn distributional fluency or recurring sign patterns without establishing what those signs mean in the world.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Tom Di Mino publicly claimed in June 2026 that he had deciphered Linear A.  ·  read in full (as of 2026-07-31)
- _[unconfirmed]_ Di Mino's proposed interpretation places the language of Linear A within an extinct Semitic language related to Hebrew, Arabic, and Aramaic.  ·  read in full (as of 2026-07-31)
- _[unconfirmed]_ Di Mino's approach began with a proposed Semitic interpretation of a recurring word in Linear A sanctuary or libation inscriptions, associated with a root meaning 'to dwell' or 'to inhabit'.  ·  read in full (as of 2026-07-31)
- _[likely]_ Di Mino used AI-assisted programming scripts, including Claude Code, to query and cross-reference Linear A material from the GORILA and SigLA corpora.  ·  read in full (as of 2026-07-31)
- _[unconfirmed]_ Di Mino says his analysis produced proposed readings for 40 Linear A signs and a lexicon of approximately 400 to 408 translated terms.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Di Mino's work was described as a draft manuscript rather than a peer-reviewed publication.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ The Di Mino claim had not been independently confirmed as a decipherment by the sources consulted by 2026-07-30.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Di Mino's public first-party software trail currently documents a claimed Linear A sign-registry and research workflow, but the inspected repository is primarily a Claude Code configuration repository rather than an archival release of the claimed decipherment.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ The inspected first-party commit describes proposed research infrastructure—334 signs, polyphonic readings, cross-script mappings, Proto-Semitic root searches, and named analysis tools—but does not expose the full Ya Diktu manuscript, complete sign-value tables, corpus snapshot, preprocessing record, complete lexicon, translations, or submission history.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ No bilingual inscription has been found that provides Linear A with a decisive equivalent of the Rosetta Stone.  ·  read in full (as of 2026-07-31)
- _[likely]_ The surviving Linear A evidence consists of roughly 1,500 inscriptions and about 7,500 sign characters, with much of it short, formulaic, damaged, or administratively repetitive.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ In Linear A, a sign's function may depend on context: signs can operate as syllabograms, logograms, transaction signs, or fractions, and SigLA records uncertain readings, unknown word boundaries, and cases where the sign function is unclear or subject to revision.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ SigLA describes Linear A as still undeciphered and says its approximate phonetic readings arise by retrospectively applying Linear B values to graphically comparable signs under a homomorphy–homophony hypothesis; this procedure supplies approximate readings of sign sequences, not established Linear A meanings.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Computational decipherment results are easier to validate when a related language, bilingual text, known cognate list, or other external anchor exists.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ AI-based decipherment methods generally use constraints such as regular sound change, monotonic character correspondences, sparse mappings, and cognate relationships.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Luo, Cao, and Barzilay's 2019 neural system correctly translated 67.3% of cognates in a Linear B to ancient Greek benchmark.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Luo, Cao, and Barzilay's 67.3% Linear B result is accuracy on cognate identification in the Linear B/names benchmark, not accuracy on unanchored Linear A decipherment. The benchmark contains 919 retained Linear B–Greek pairs, while the names condition supplies 455 Greek proper names and leaves roughly half of the Linear B vocabulary unpaired.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ The 2019 neural system reported a 5-percentage-point improvement over prior results on Ugaritic decipherment.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ The ACL 2019 experiment assumes a known related-language side—Ancient Greek for Linear B and Hebrew for Ugaritic—and evaluates word-level cognate alignment under imposed structural and phonological constraints. It therefore demonstrates performance on an externally anchored or partially anchored task, not independent discovery of a language family, grammar, and meaning from Linear A alone.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Luo et al.'s 2021 TACL method explicitly separates deciphered-language evaluation from genuinely incomplete cases: Gothic and Ugaritic provide fuller ground-truth evaluation, while Iberian lacks complete ground truth and is assessed using limited facts such as personal names and language-closeness behavior.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ The TACL paper's 75% Iberian result is precision-at-10 for a personal-name experiment with partial external knowledge, not a corpus-wide translation or decipherment result; the authors state that reliable segmentation for a true isolate remains beyond the demonstrated scope.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Open digital resources such as SigLA make systematic paleographic and statistical analysis of Linear A more feasible than reliance on printed corpora alone.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ A computational system can accelerate hypothesis generation and testing without independently generating the initial linguistic insight.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ The 2025 coupled-simulated-annealing study reported improved cognate-identification performance across several benchmark datasets but stated that real decipherment still faces scarce, damaged, poorly segmented corpora and uncertain cognate inventories.  ·  read in full (as of 2026-07-31)
- _[confirmed]_ Ancient-language machine learning suffers from data scarcity, incomplete digitization, imbalanced datasets, lack of ground truth, and possible circularity when existing scholarly judgments are used as labels.  ·  read in full (as of 2026-07-31)

---
title: CISA warns SharePoint Server Subscription Edition, 2019, and 2016 are under active exploitation—patches plus compromise hunting needed
dek: The alert is for supported on-prem SharePoint Server versions and includes CISA’s recommended sequence (hunt for intrusion artifacts before rotating IIS machine keys) and detection steps like AMSI integration, deeper request scanning, and webshell/machine-key checks.
date: '2026-07-18'
published_at: '2026-07-18T22:26:08.796461+00:00'
as_of: '2026-07-17'
status: blocked
tags:
- economics
- SharePoint Server
- Known Exploited Vulnerabilities (KEV) Catalog
- IIS machine keys
- AMSI
thumbnail: /analytics/cisa-warns-sharepoint-server-subscription-edition-2019-and-2-1d951d/analytic_req_1.svg
---

CISA says multiple SharePoint Server vulnerabilities are being actively exploited in the wild against supported on-premises deployments: SharePoint Server Subscription Edition, 2019, and 2016.

That boundary matters. The alert is about on-prem servers, not cloud SharePoint, and CISA’s guidance makes direct internet exposure an operational priority rather than a separately confirmed scope fact. If a SharePoint server is directly exposed, it should move up the list — but the confirmed affected set is the supported on-prem line.

The reason this is more than a routine patch notice is the behavior CISA says it has seen or expects. The alert ties the activity to remote code execution, unauthorized access, IIS machine-key theft, deserialization, persistence, and malware deployment. Microsoft’s CVE-2026-58644 page identifies the issue as a SharePoint remote code execution flaw, marks it as exploited, and says an attacker authenticated as at least a Site Owner could write arbitrary code and execute it remotely.

So the response is not just install updates and move on. CISA says operators should apply Microsoft’s patches, verify installation, and shorten patch cycles where possible. It also says to enable AMSI integration for each SharePoint web application and use Full Mode for request-body scanning where feasible, improve logging, watch for anomalous requests and suspicious SharePoint worker-process activity, and look for webshells and machine-key access.

CISA is also explicit about sequence: before rotating IIS machine keys, hunt for and remediate intrusion artifacts, including machine-key harvesters that could let attackers steal them again. And if SharePoint has to stay exposed, CISA wants it behind a Layer 7 reverse proxy or equivalent application-layer control that requires authentication and can inspect and filter requests.

KEV listing is a severity signal, and for FCEB agencies it also carries a specific remediation clock. But for most operators, the more important point is narrower and harsher: patching may be necessary without being sufficient.

What remains unresolved is just as important. CISA does not name an actor or malware family, and the sources here do not establish whether the four exploited CVEs are one chain, parallel flaws, or separate parts of a broader wave. CISA also draws a boundary around at least one newly disclosed SharePoint CVE that it says is not yet known to have been exploited. The safe reading is active compromise risk, not a finished campaign narrative.

**SharePoint exploitation timeline for the KEV and MS patch window**

![SharePoint exploitation timeline for the KEV and MS patch window](/analytics/cisa-warns-sharepoint-server-subscription-edition-2019-and-2-1d951d/analytic_req_1.svg)

*Microsoft released the MSRC advisory for CVE-2026-58644 on Jul 14, 2026 (last updated Jul 15), the same day CISA published its SharePoint hardening alert; CISA then added that CVE to the KEV catalog on Jul 16 and revised the alert accordingly. Three other CVEs named as actively exploited (CVE-2026-32201, CVE-2026-45659, CVE-2026-56164) appear as labels only — the profile has no KEV addition dates for them. — AI-assisted analytic, built only from cited data. Source: cited claims clm_840b6f46ce, clm_0eea7ef7c7, clm_e371bee28c, clm_8783eaa575, clm_acf1cf77cd, clm_0ef82990f9, clm_7acb5ba602. As of 2026-07-17.*

**Compromise-assessment coverage: what to hunt vs. what to patch (from CISA guidance)**

| Bucket | Definition |
|--------|------------|
| **A — Patch / verify** | Apply patches, verify installation, accelerate patch cycles |
| **B — Compromise hunt / contain** | Pre-rotation artifact hunting, AMSI, logging & anomaly watch, webshell/machine-key checks, reduce direct internet exposure |

*Based on CISA’s recommended response, what share of actions are 'patch/verify' vs 'compromise hunting/containment'—and how does that vary by SharePoint version? AI-assisted analytic, built only from cited data.*

**CISA-referenced SharePoint versions mapped to exploitation scope and key defenses**

| Version | CISA says it’s actively exploited | Post-exploitation behaviors cited | High-priority defenses |
|---|---|---|---|
| SharePoint Server Subscription Edition | Yes | Applies to all listed versions: RCE; IIS machine-key theft; deserialization; persistence; malware deployment | Recommended in advisory (not version-differentiated): • Apply Microsoft’s latest patches, verify installation, shorten patch cycles • Enable AMSI integration per SharePoint web application; Full Mode request-body scanning where feasible • Improve logging; hunt anomalous requests, suspicious worker-process activity, webshells, and machine-key access • Hunt and remediate intrusion artifacts (incl. machine-key harvesters) before rotating IIS machine keys • Avoid direct internet exposure; if exposure is required, put SharePoint behind a Layer 7 reverse proxy (or equivalent authenticated app-layer control) |
| SharePoint Server 2019 | Yes | Applies to all listed versions: RCE; IIS machine-key theft; deserialization; persistence; malware deployment | Recommended in advisory (not version-differentiated): • Apply Microsoft’s latest patches, verify installation, shorten patch cycles • Enable AMSI integration per SharePoint web application; Full Mode request-body scanning where feasible • Improve logging; hunt anomalous requests, suspicious worker-process activity, webshells, and machine-key access • Hunt and remediate intrusion artifacts (incl. machine-key harvesters) before rotating IIS machine keys • Avoid direct internet exposure; if exposure is required, put SharePoint behind a Layer 7 reverse proxy (or equivalent authenticated app-layer control) |
| SharePoint Server 2016 | Yes | Applies to all listed versions: RCE; IIS machine-key theft; deserialization; persistence; malware deployment | Recommended in advisory (not version-differentiated): • Apply Microsoft’s latest patches, verify installation, shorten patch cycles • Enable AMSI integration per SharePoint web application; Full Mode request-body scanning where feasible • Improve logging; hunt anomalous requests, suspicious worker-process activity, webshells, and machine-key access • Hunt and remediate intrusion artifacts (incl. machine-key harvesters) before rotating IIS machine keys • Avoid direct internet exposure; if exposure is required, put SharePoint behind a Layer 7 reverse proxy (or equivalent authenticated app-layer control) |

*For each affected SharePoint Server version in the advisory (Subscription Edition, 2019, 2016), what is the supported on-prem exploitation scope CISA describes, and which high-priority defenses are universally recommended? AI-assisted analytic, built only from cited data.*

---
## How we know this

**How this piece is framed:** A defensive operations frame with a hard boundary between confirmed scope and inferred priority: this is an active exploitation event against named supported on-prem SharePoint Server versions, and the reader needs to see both the patching task and the compromise-hunting task — while keeping clear that internet exposure is an operational priority inferred from CISA’s mitigation guidance, not a separately confirmed scope fact.

**Charts & tables** — _each built only from the cited claims below, by an AI tool_
- SharePoint exploitation timeline for the KEV and MS patch window — from claims clm_840b6f46ce, clm_0eea7ef7c7, clm_e371bee28c, clm_8783eaa575, clm_acf1cf77cd, clm_0ef82990f9, clm_7acb5ba602 · as of 2026-07-17
- Compromise-assessment coverage: what to hunt vs. what to patch (from CISA guidance) — from claims clm_c4415ede07, clm_0c0a526656, clm_de87c3643d, clm_839f6fd01c, clm_f947659527, clm_3528561cb3, clm_53b71a5661, clm_20d0b1fb4f, clm_7783ed6309 · as of 2026-07-17 · ⚠ figures not all matched to the cited claims: 30.0, 70.0
- CISA-referenced SharePoint versions mapped to exploitation scope and key defenses — from claims clm_f6b0cb6c3b, clm_be05c99c1a, clm_7783ed6309, clm_f48a4c8e57, clm_071668ba4c, clm_c4415ede07, clm_de87c3643d, clm_839f6fd01c, clm_f947659527, clm_3528561cb3, clm_20d0b1fb4f, clm_53b71a5661 · as of 2026-07-17

**Sources**
- (primary) CISA Urges SharePoint Hardening After New Exploitations — https://www.cisa.gov/news-events/alerts/2026/07/14/cisa-urges-sharepoint-hardening-after-new-exploitations  ·  _read in full · captured 2026-07-18_
- (primary) Microsoft Security Update Guide — CVE-2026-58644 — https://msrc.microsoft.com/update-guide/vulnerability/CVE-2026-58644  ·  _read in full · captured 2026-07-18_

**Claims, and how far we tracked each down**
- _[confirmed]_ CISA says multiple SharePoint Server vulnerabilities are being actively exploited in the wild against supported on-premises deployments: SharePoint Server Subscription Edition, 2019, and 2016.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA recommends avoiding direct internet exposure of SharePoint Servers when possible and using a Layer 7 reverse proxy or equivalent application-layer control if exposure is necessary.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ The exploitation path can enable remote code execution and post-exploitation activity on affected SharePoint servers.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA specifically cites stealing IIS machine keys and using deserialization techniques as part of post-exploitation activity that can support persistence and malware deployment.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ Microsoft’s MSRC page marks CVE-2026-58644 as exploited and lists the exploitability assessment as Exploitation Detected.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ Microsoft’s MSRC page says CVE-2026-58644 was publicly disclosed as no and includes FAQ text indicating the vulnerability can be exploited over the network by an attacker authenticated as at least a Site Owner.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA recommends applying Microsoft’s latest patches and security updates, verifying installation, and shortening patch cycles.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA recommends enabling AMSI integration for each SharePoint web application and using Full Mode for request-body scanning where feasible.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA recommends tailored logging, review for anomalous requests, suspicious SharePoint worker-process activity, webshells, and machine-key access.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA recommends hunting for intrusion artifacts before rotating IIS machine keys.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ If SharePoint has to stay exposed, CISA wants it behind a Layer 7 reverse proxy or equivalent application-layer control that requires authentication and can inspect and filter requests.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA added CVE-2026-58644 to the KEV catalog on July 16, 2026, according to the updated advisory.  ·  read in full (as of 2026-07-18)
- _[likely]_ KEV listing is a severity signal, and for FCEB agencies it also carries a specific remediation clock.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ CISA does not name an actor or malware family, and the sources here do not establish whether the four exploited CVEs are one chain, parallel flaws, or separate parts of a broader wave.  ·  read in full (as of 2026-07-18)
- _[confirmed]_ The same CISA alert also draws an explicit boundary around at least one newly disclosed SharePoint CVE, saying it is not yet known to have been exploited even though Microsoft identified it as a potential risk if left unpatched.  ·  read in full (as of 2026-07-18)

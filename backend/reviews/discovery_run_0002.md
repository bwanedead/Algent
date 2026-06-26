# Discovery run review — rake output → final vectors

Run `0002` (c489d0ef). Funnel: **t0 65 → rake 58 → synthesis cited 15 → 4 vectors**.  Run cost ~$0.12 (rake ~$0.0047).

- rake dropped **7** (non-news / promo / taxonomy noise)
- synthesis used **15** of the 58, dropped **43** as the long tail

**Synthesis drop note:** Dropped promotional, celebrity, and low-signal local churn; also dropped weakly related items that did not support a durable research pipeline. Some non-t0 corroboration was used only to validate major macro threads where the pool itself was indirect.

---

## The 58 hits that passed rake

### GKG net themes/entities — 33 items (5 used by a vector)

| # | label | signals | outcome |
|---|-------|---------|---------|
| 1 | TAX_WORLDFISH_COD | velocity=3.174 rising=True language_count=6 count=22 | _dropped by synthesis_ |
| 2 | EPU_POLICY_FISCAL_POLICY | velocity=3.5 rising=True novel=True language_count=5 count=7 | _dropped by synthesis_ |
| 3 | WB_655_INFORMATION_MANAGEMENT | velocity=5.0 rising=True novel=True language_count=4 count=1 | → **V4** |
| 4 | GOV_WIRETAPPING | velocity=3.632 rising=True language_count=4 count=9 | _dropped by synthesis_ |
| 5 | WB_872_SMART_CITIES | velocity=2.5 rising=True novel=True language_count=5 count=5 | _dropped by synthesis_ |
| 6 | queen camilla | velocity=2.852 rising=True language_count=4 count=11 | _dropped by synthesis_ |
| 7 | king charles | velocity=2.529 rising=True language_count=5 count=13 | _dropped by synthesis_ |
| 8 | WB_1150_VOLATILITY | velocity=1.636 rising=True language_count=12 count=55 | → **V2** |
| 9 | WB_2811_COLLECTIVE_BARGAINING | velocity=4.5 rising=True novel=True language_count=3 count=9 | → **V2** |
| 10 | WB_829_FISCAL_DECENTRALIZATION | velocity=3.444 rising=True language_count=3 count=23 | → **V3** |
| 11 | ENV_COAL | velocity=1.842 rising=True language_count=8 count=25 | _dropped by synthesis_ |
| 12 | WB_1463_HEALTH_EDUCATION | velocity=2.368 rising=True language_count=5 count=6 | _dropped by synthesis_ |
| 13 | WB_1075_INDUSTRY_POLICY | velocity=2.478 rising=True language_count=4 count=8 | → **V2, V4** |
| 14 | TAX_TERROR_GROUP_TALIBAN | velocity=2.2 rising=True language_count=5 count=6 | _dropped by synthesis_ |
| 15 | sergei sobyanin | velocity=2.385 rising=True language_count=4 count=9 | _dropped by synthesis_ |
| 16 | MANMADE_DISASTER_TRAFFIC_ACCIDENT | velocity=2.059 rising=True language_count=5 count=11 | _dropped by synthesis_ |
| 17 | TAX_DISEASE_COMA | velocity=2.5 rising=True novel=True language_count=3 count=5 | _dropped by synthesis_ |
| 18 | municipal police | velocity=2.5 rising=True novel=True language_count=3 count=5 | _dropped by synthesis_ |
| 19 | CONFISCATION | velocity=1.353 rising=True language_count=12 count=28 | _dropped by synthesis_ |
| 20 | WB_1918_SECURITIES_MARKETS | velocity=2.259 rising=True language_count=4 count=9 | _dropped by synthesis_ |
| 21 | ketan agarwal | velocity=4.5 rising=True novel=True language_count=2 count=9 | _dropped by synthesis_ |
| 22 | imperial college london | velocity=3.5 rising=True novel=True language_count=2 count=7 | _dropped by synthesis_ |
| 23 | WB_1441_SUPPLEMENTS | velocity=1.007 rising=True language_count=23 count=69 | _dropped by synthesis_ |
| 24 | yogi adityanath | velocity=3.5 rising=True novel=True language_count=2 count=7 | _dropped by synthesis_ |
| 25 | public service | velocity=3.0 rising=True novel=True language_count=2 count=6 | _dropped by synthesis_ |
| 26 | WB_1623_PRICE_SUBSIDIES | velocity=3.5 rising=True novel=True language_count=2 count=7 | _dropped by synthesis_ |
| 27 | head office | velocity=3.0 rising=True novel=True language_count=2 count=6 | _dropped by synthesis_ |
| 28 | sergey brin | velocity=4.0 rising=True novel=True language_count=2 count=8 | _dropped by synthesis_ |
| 29 | ECON_WORLDCURRENCIES_YEN | velocity=1.667 rising=True language_count=7 count=12 | _dropped by synthesis_ |
| 30 | carlos alvarado | velocity=2.52 rising=True language_count=3 count=9 | _dropped by synthesis_ |
| 31 | WB_2946_OPEN_SOURCE | velocity=2.52 rising=True language_count=3 count=9 | _dropped by synthesis_ |
| 32 | WB_2934_COPPER | velocity=1.569 rising=True language_count=7 count=33 | _dropped by synthesis_ |
| 33 | WB_2120_SATELLITES | velocity=1.043 rising=True language_count=19 count=57 | _dropped by synthesis_ |

### Polymarket leads — 25 items (10 used by a vector)

| # | label | signals | outcome |
|---|-------|---------|---------|
| 1 | Will Benjamin Netanyahu enter Iran by June 30? | volume_24h=3122541.56 | → **V1** |
| 2 | Will Adanech Abiebie be the next Prime Minister of Ethiopia? | volume_24h=3009506.94 price_change_1d=-0.01 | _dropped by synthesis_ |
| 3 | Strait of Hormuz traffic returns to normal by end of June? | volume_24h=2340927.06 price_change_1d=0.09 | → **V1** |
| 4 | Strait of Hormuz traffic returns to normal by July 31? | volume_24h=954185.03 price_change_1d=0.1 | → **V1** |
| 5 | Kharg Island no longer under Iranian control by June 30? | volume_24h=814118.11 | _dropped by synthesis_ |
| 6 | Will the Fed increase interest rates by 50+ bps after the Ju | volume_24h=805560.36 | _dropped by synthesis_ |
| 7 | Strait of Hormuz traffic returns to normal by July 15? | volume_24h=782168.23 price_change_1d=0.1 | → **V1** |
| 8 | Will Crude Oil (CL) hit (HIGH) $200 by end of June? | volume_24h=687870.87 | → **V1** |
| 9 | Will the Fed decrease interest rates by 25 bps after the Jul | volume_24h=641185.21 | _dropped by synthesis_ |
| 10 | Will the US confirm that aliens exist by June 30? | volume_24h=627805.73 | _dropped by synthesis_ |
| 11 | Will Ayo Dosunmu play for the Oklahoma City Thunder in 2026- | volume_24h=474780.01 | _dropped by synthesis_ |
| 12 | Putin out as President of Russia by December 31, 2026? | volume_24h=464270.43 price_change_1d=0.03 | _dropped by synthesis_ |
| 13 | Will Bitcoin dip to $57,500 in June? | volume_24h=430215.38 price_change_1d=0.21 | _dropped by synthesis_ |
| 14 | Will Jared Kushner enter Iran by June 30? | volume_24h=418310.93 | → **V1** |
| 15 | Will Ayo Dosunmu play for the Orlando Magic in 2026-27? | volume_24h=377845.01 | _dropped by synthesis_ |
| 16 | Will there be no change in Fed interest rates after the July | volume_24h=372962.86 price_change_1d=0.06 | _dropped by synthesis_ |
| 17 | US-Iran Final Nuclear Deal by August 31, 2026? | volume_24h=343578.81 price_change_1d=0.02 | → **V1** |
| 18 | Will the Iranian regime fall by June 30? | volume_24h=332907.13 | → **V1** |
| 19 | Will the price of Bitcoin be above $58,000 on June 26? | volume_24h=320685.53 price_change_1d=-0.06 | _dropped by synthesis_ |
| 20 | Will Brandon Aiyuk play for New England Patriots in 2026-27? | volume_24h=308803.08 price_change_1d=-0.03 | _dropped by synthesis_ |
| 21 | Will 60 ships transit the Strait of Hormuz on any day by Jun | volume_24h=308205.35 price_change_1d=0.25 | → **V1** |
| 22 | Will the Fed increase interest rates by 25 bps after the Jul | volume_24h=274408.37 price_change_1d=-0.06 | _dropped by synthesis_ |
| 23 | Will Hunter Biden win the 2028 Democratic presidential nomin | volume_24h=272995.96 | _dropped by synthesis_ |
| 24 | Will the price of Bitcoin be above $62,000 on June 26? | volume_24h=248493.97 price_change_1d=-0.38 | _dropped by synthesis_ |
| 25 | Saudi Arabia bans US military aircraft by June 30? | volume_24h=245654.65 | → **V1** |

---

## The 4 research vectors (t1)

### V1. Strait of Hormuz escalation/de-escalation as a global oil and shipping risk

- **type / effort:** story / standard
- **thesis:** The real story is whether Hormuz shipping is truly normalizing or still hostage to Iran-Israel-US ceasefire terms. That directly affects oil, freight, insurance, and near-term geopolitical risk pricing.
- **why:** Highest-leverage market-moving thread in the pool. Multiple market contracts point to the same underlying event: a volatile Hormuz shipping lane with direct consequences for crude and maritime risk.
- **supporting hits (10):**
    - `market:polymarket:traffic-returns-to-normal-by-end-of-june` — Strait of Hormuz traffic returns to normal by end of June?
    - `market:polymarket:muz-traffic-returns-to-normal-by-july-31` — Strait of Hormuz traffic returns to normal by July 31?
    - `market:polymarket:muz-traffic-returns-to-normal-by-july-15` — Strait of Hormuz traffic returns to normal by July 15?
    - `market:polymarket:ait-of-hormuz-on-any-day-by-june-30-2026` — Will 60 ships transit the Strait of Hormuz on any day by June 30, 2026
    - `market:polymarket:e-oil-cl-hit-high-200-by-end-of-june-677` — Will Crude Oil (CL) hit (HIGH) $200 by end of June?
    - `market:polymarket:deal-by-august-31-2026-20260621201255154` — US-Iran Final Nuclear Deal by August 31, 2026?
    - `market:polymarket:/will-the-iranian-regime-fall-by-june-30` — Will the Iranian regime fall by June 30?
    - `market:polymarket:benjamin-netanyahu-enter-iran-by-june-30` — Will Benjamin Netanyahu enter Iran by June 30?
    - `market:polymarket:will-jared-kushner-enter-iran-by-june-30` — Will Jared Kushner enter Iran by June 30?
    - `market:polymarket:bia-bans-us-military-aircraft-by-june-30` — Saudi Arabia bans US military aircraft by June 30?
- **key questions:**
    - Is traffic actually recovering, or are headlines running ahead of facts?
    - What terms are tying reopening to Lebanon ceasefire/oil waivers?
    - How are oil, tanker insurance, and freight rates reacting?
    - What scenarios remain for further disruption through July?
- **sources:** https://www.reuters.com/world/middle-east/irans-tasnim-news-agency-says-hormuz-will-not-reopen-until-lebanon-ceasefire-2026-06-21/, https://cryptobriefing.com/trump-maritime-traffic-resumes-in-strait-of-hormuz-after-us-iran-ceasefire/

### V2. Germany’s industrial labor-cost reset: hours, protections, and AI productivity

- **type / effort:** synthesis / deep
- **thesis:** Mercedes is the signal, but the underlying story is a broader German industrial competitiveness squeeze that is forcing a renegotiation of labor norms: longer hours, weaker job protections, AI-led productivity, and cost cuts across autos and manufacturing.
- **why:** This fuses company-level labor talks into a structural Europe/Germany industry story with implications for margins, wages, and the future bargaining position of labor.
- **supporting hits (3):**
    - `gkg:theme:WB_2811_COLLECTIVE_BARGAINING` — WB_2811_COLLECTIVE_BARGAINING
    - `gkg:theme:WB_1075_INDUSTRY_POLICY` — WB_1075_INDUSTRY_POLICY
    - `gkg:theme:WB_1150_VOLATILITY` — WB_1150_VOLATILITY
- **key questions:**
    - Is Mercedes an isolated negotiation or the opening move in a wider wage-hours reset?
    - How common are similar talks at BMW, Volkswagen, and suppliers?
    - How much of the pressure comes from China demand, tariffs, EV transition, and domestic cost structure?
    - What role is AI already playing in headcount and process redesign?
    - Could this spread beyond autos into other German manufacturing sectors?
- **sources:** https://www.automotiveworld.com/news/mercedes-opens-talks-to-loosen-german-job-protections/, https://finance.yahoo.com/economy/policy/articles/mercedes-chairman-calls-return-40-095642469.html, https://www.just-auto.com/news/mercedes-cost-cutting-labour-representatives/

### V3. Germany pension overhaul: retirement age, funded pillar, and redistribution

- **type / effort:** analytic / deep
- **thesis:** The German pension commission package is a major structural reform attempt: later retirement, abolition of early-retirement perks, a mandatory funded pillar, and a rebalancing of costs between workers, retirees, employers, and the state.
- **why:** A first-order policy shift with fiscal, labor-market, and capital-market consequences. It also connects to intergenerational politics and long-run social cohesion.
- **supporting hits (1):**
    - `gkg:theme:WB_829_FISCAL_DECENTRALIZATION` — WB_829_FISCAL_DECENTRALIZATION
- **key questions:**
    - Which recommendations are politically feasible in the coalition?
    - How large will the funded pillar be in practice?
    - Who bears the adjustment cost: workers, employers, pensioners, or the federal budget?
    - What happens to the retirement-age path and early-retirement regimes?
    - How do unions and business groups split on the package?
- **sources:** https://www.bundesregierung.de/resource/blob/975228/2444780/0fcbf810775351c64007ee6cb2c7cad9/2026-06-24-bericht-alterssicherungskommission-data.pdf?download=1, https://www.reuters.com/world/americas/brazil-plans-up-5-billion-yuan-panda-bond-issuance-says-finance-minister-2026-06-25/, https://www.dw.com/en/germanys-pension-plans-draw-praise-and-outrage/a-77663371, https://www.thestar.com.my/news/world/2026/06/23/german-pension-commission-proposes-shift-to-swedish-style-fund, https://www.zew.de/en/press/latest-press-releases/pension-commission-presents-final-report

### V4. German corporate pensions / workforce coverage expansion as a hidden labor-market lever

- **type / effort:** implications / standard
- **thesis:** Beyond the headline state-pension reform, the medium-term change may be the push to expand occupational pensions and standardize coverage in SMEs and low-wage sectors, reshaping labor costs and worker retention.
- **why:** This is the implementation layer that determines whether pension reform actually changes household replacement rates and firm costs.
- **supporting hits (2):**
    - `gkg:theme:WB_1075_INDUSTRY_POLICY` — WB_1075_INDUSTRY_POLICY
    - `gkg:theme:WB_655_INFORMATION_MANAGEMENT` — WB_655_INFORMATION_MANAGEMENT
- **key questions:**
    - Will occupational pensions be made easier via opt-out or automatic enrollment?
    - What burden does expanded coverage place on SMEs?
    - Does this meaningfully raise retirement adequacy for low earners?
    - How does it interact with the proposed funded first pillar?
- **sources:** https://www.pensionpolicyinternational.com/german-reforms-could-see-e400bn-private-pension-boost/, https://www.thelocal.de/20260623/what-germanys-planned-pension-reform-means-for-you


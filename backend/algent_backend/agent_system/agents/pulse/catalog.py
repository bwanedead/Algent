"""
The seed situations — where Ohmega's model of the world starts.

Seed nodes, not a permanent taxonomy: situations split and merge later with provenance kept
(docs/architecture/pulse-system.md). Each carries a SCOPE note so attaching research to it is a
judgment against a stated boundary, not a vibe. Eight well-kept situations beat thirty shallow ones.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedSituation:
    id: str
    title: str
    scope: str
    domain: str = "geopolitics"


SEED_SITUATIONS: tuple[SeedSituation, ...] = (
    SeedSituation("sit_russia_nato", "Russia–NATO confrontation",
                  "Direct military, hybrid and diplomatic friction between Russia and NATO/EU "
                  "states: airspace and sea incidents, sabotage, force posture on the eastern "
                  "flank, deterrence signalling. Not the fighting inside Ukraine itself."),
    SeedSituation("sit_ukraine_war", "The war in Ukraine",
                  "The war on Ukrainian territory: front lines, strikes on cities and energy, "
                  "mobilisation, Western military and financial support, ceasefire diplomacy."),
    SeedSituation("sit_iran_gulf", "Iran, Israel and the Gulf",
                  "Iran's confrontation with Israel and the US, the Strait of Hormuz and Gulf "
                  "security, Iran's regional proxies (Houthis, Hezbollah), talks and ceasefires."),
    SeedSituation("sit_china_taiwan", "China–Taiwan",
                  "PLA pressure on Taiwan, cross-strait politics, US and allied commitments, "
                  "blockade and invasion risk, Taiwan's defence posture."),
    SeedSituation("sit_us_china", "US–China competition",
                  "Trade, tariffs, export controls, technology and chips, finance, diplomacy and "
                  "summits between the US and China. Taiwan-specific military pressure lives in "
                  "China–Taiwan."),
    SeedSituation("sit_israel_palestine", "Israel–Palestine and the wider region",
                  "Gaza, the West Bank, settlements, the humanitarian situation, normalisation "
                  "and regional diplomacy, and international legal and diplomatic pressure on "
                  "Israel."),
    SeedSituation("sit_sahel_horn", "Sahel and Horn of Africa instability",
                  "Coups, insurgencies and state fragility across the Sahel and the Horn "
                  "(Mali, Burkina Faso, Niger, Sudan, Ethiopia, Somalia), foreign military "
                  "presence and displacement."),
    SeedSituation("sit_red_sea_shipping", "Red Sea and global shipping disruption",
                  "Threats to commercial shipping through chokepoints — Bab el-Mandeb, Suez, "
                  "Hormuz as a shipping lane — rerouting, insurance, freight costs, naval "
                  "escorts. The political confrontation lives in Iran, Israel and the Gulf."),
    SeedSituation("sit_energy_security", "Global energy security",
                  "Oil and gas supply and prices, OPEC+ decisions, strategic reserves, supply "
                  "disruptions, and the energy transition's effect on supply security."),
    SeedSituation("sit_ai_geopolitics", "AI geopolitics",
                  "Frontier AI as a strategic contest: compute and chip controls, state AI "
                  "strategies, military AI, AI safety governance and incidents with state "
                  "consequences."),
)

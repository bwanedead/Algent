"""
Plain-English notes for the actor metrics a reader meets in the numbers panel (what it is, why it matters, <= 2
sentences). Only the opaque ones are here: a label like "Population" explains itself. Published beside the metric
(``agents/intel/numbers.actor_block``) so the site's info tips read the one source.
"""

from __future__ import annotations

PLAIN: dict[str, str] = {
    "gdp": "The total value of everything the country produces in a year, in US dollars. It is the standard measure of economic size.",
    "gdp_pc": "GDP divided by population: roughly how much output there is per person. It says more about living standards than total size does.",
    "gdp_growth": "How much the economy grew (or shrank) over the year, after removing price rises. Slow growth strains budgets and politics.",
    "energy_production": "All the oil, gas and coal the country digs or pumps in a year, counted in terawatt-hours of energy. It shows whether the country feeds itself or depends on imports.",
    "energy_use": "All the energy the country consumes in a year, in terawatt-hours. Set against production, it shows how exposed the country is to supply shocks.",
    "energy_import_pct": "The share of the energy the country uses that it has to buy from abroad. A high share means a cut-off or a price spike hurts quickly.",
    "fuel_exports_pct": "The share of the country's goods exports that are oil, gas and coal. A high share means the budget rises and falls with energy prices.",
    "gov_debt_imf": "What the whole government owes, as a share of a year of national output. Higher means less room to borrow in a crisis.",
    "fiscal_balance_imf": "How much the government spends beyond (negative) or below (positive) what it collects, as a share of GDP. Persistent deficits pile up as debt.",
    "current_account_imf": "The country's net trade and income with the rest of the world, as a share of GDP. A big deficit means it relies on foreign money to pay its way.",
    "reserves_usd": "The foreign currency and gold the central bank holds. It is the cushion for defending the currency and paying for imports in a crisis.",
    "reserves_months": "How many months of imports the reserves would cover. Under three months is usually considered thin.",
    "ext_debt_usd": "What the country owes to foreign lenders, public and private. Debt in foreign currency gets harder to pay when the home currency falls.",
    "ext_debt_gni": "Foreign debt as a share of national income. The higher it is, the more of the economy must go to paying outsiders.",
    "policy_rate": "The central bank's main interest rate at year end. Raising it fights inflation but slows the economy.",
    "milex": "What the government spends on its military in a year, in US dollars. It is the headline measure of military effort.",
    "milex_pct": "Military spending as a share of GDP. It shows how heavily the economy is weighed toward defence, whatever its size.",
    "armed_forces": "The number of people in uniform, including paramilitary forces. It is a rough gauge of manpower, not of quality.",
}

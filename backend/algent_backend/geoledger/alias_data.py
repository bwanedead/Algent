"""
Curated spelling groups: names the desk meets for ONE plant that no transliteration rule can join (an abbreviation, a
town for an adjective, a unit number for a district name). Each group is names of the same plant; ``alias.variants``
adds a group's other members whenever a name of the text equals one of them (script and ending folded, plant kind and
unit number kept).

Add a group only when the equivalence is a naming fact. A wrong entry merges two plants and hangs one's status on the
other; a missing entry only costs a duplicate that ``newsroom geo merge`` can join later. Latin spellings suffice:
Cyrillic forms transliterate to them.
"""

from __future__ import annotations

CURATED: tuple[tuple[str, ...], ...] = (
    ("Zaporizhzhia NPP", "Zaporizhia NPP", "Zaporizhzhya NPP", "Zaporozhye NPP", "ZNPP", "ZAES", "Zaporizka AES"),
    ("Chornobyl NPP", "Chernobyl NPP", "ChNPP", "Chornobyl AES"),
    ("Dnipro HPP", "Dnieper HPP", "DniproHES", "Dnipro HES", "Zaporizhzhia HPP"),
    ("Trypilska TPP", "Trypillya TPP", "Trypilska TES", "Trypillia TPP"),
    ("Zmiivska TPP", "Zmiyivska TPP", "Zmiiv TPP", "Zmiev TPP", "Zmiivska TES"),
    ("Vuhlehirska TPP", "Uglegorsk TPP", "Uglegorskaya TPP", "Vuhlehirsk TPP", "Vuhlehirska TES"),
    ("Sloviansk TPP", "Slovianska TPP", "Slavyansk TPP", "Slavyanskaya TPP"),
    ("Kurakhove TPP", "Kurakhivska TPP", "Kurakhovskaya TPP"),
    ("Kursk NPP", "Kurskaya NPP", "Kurskaya AES", "Kurchatov NPP"),
    # Named by the desk's brief: the Kyiv district plant is also called by its number.
    ("Darnytska CHP", "Darnytska CHP-4", "Kyiv CHP-4", "Kyiv TETs-4", "Darnitsa CHP"),
)

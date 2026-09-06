"""Rules for deriving a card's German name from its English name, so that
predictable variants ("X ex", "Mega X ex", "Team Rocket's X", "Hisuian X",
"Alolan X", "Galarian X", "Paldean X") don't each need their own entry in
data/card_translations.csv -- only the base Pokémon name does.

An exact entry in the lookup table always wins over derivation, so genuine
exceptions (cards whose official German name doesn't follow the mechanical
pattern) are handled by simply adding a full override row for that exact
name.
"""

AFFIX_RULES = [
    ("suffix", " ex", "-ex"),
    ("prefix", "Mega ", "Mega-"),
    ("prefix", "Team Rocket's ", "Team Rockets "),
    ("prefix", "Hisuian ", "Hisui-"),
    ("prefix", "Alolan ", "Alola-"),
    ("prefix", "Galarian ", "Galar-"),
    ("prefix", "Paldean ", "Paldea-"),
]


def derive_translation(name: str, lookup: dict[str, str]) -> str | None:
    """Return the German name for *name*, or None if it can't be resolved.

    Checks *lookup* for an exact match first (the override escape hatch),
    then recursively strips one recognised affix at a time -- this handles
    composed cases (e.g. "Mega Absol ex") without special-casing them.
    """
    if name in lookup:
        return lookup[name]
    for kind, en_affix, de_affix in AFFIX_RULES:
        if kind == "suffix" and name.endswith(en_affix):
            base_translation = derive_translation(name[: -len(en_affix)], lookup)
            if base_translation:
                return base_translation + de_affix
        elif kind == "prefix" and name.startswith(en_affix):
            base_translation = derive_translation(name[len(en_affix) :], lookup)
            if base_translation:
                return de_affix + base_translation
    return None

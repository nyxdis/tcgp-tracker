from apps.tracker.card_name_rules import derive_translation


def test_exact_match_takes_precedence():
    lookup = {"Bulbasaur": "Bisasam", "Bulbasaur ex": "Overridden"}
    assert derive_translation("Bulbasaur ex", lookup) == "Overridden"


def test_suffix_rule():
    lookup = {"Bulbasaur": "Bisasam"}
    assert derive_translation("Bulbasaur ex", lookup) == "Bisasam-ex"


def test_prefix_rule():
    lookup = {"Vulpix": "Vulpix"}
    assert derive_translation("Alolan Vulpix", lookup) == "Alola-Vulpix"


def test_composed_prefix_and_suffix():
    lookup = {"Absol": "Absol"}
    assert derive_translation("Mega Absol ex", lookup) == "Mega-Absol-ex"


def test_team_rockets_prefix():
    lookup = {"Arbok": "Arbok"}
    assert derive_translation("Team Rocket's Arbok", lookup) == "Team Rockets Arbok"


def test_unresolvable_returns_none():
    lookup = {"Bulbasaur": "Bisasam"}
    assert derive_translation("Charizard ex", lookup) is None
    assert derive_translation("Unrelated Name", lookup) is None

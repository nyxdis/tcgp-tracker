"""Management command to scrape pocket.pokemongohub.net and update data/ CSV files.

Fetches set, card, and pack data for all non-promo sets and writes the results
into data/sets.csv, data/cards.csv, data/set_translations.csv,
data/pack_translations.csv, and data/card_translations.csv.
Only rows that do not already exist are added; existing rows are preserved.
"""

import csv
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

BASE_URL = "https://pocket.pokemongohub.net"
DATA_DIR = Path(__file__).resolve().parents[4] / "data"

# Maps heading text keywords (lower-case, normalised) to internal rarity names.
RARITY_HEADING_MAP = {
    "1-diamond": "common",
    "2-diamond": "uncommon",
    "3-diamond": "rare",
    "4-diamond": "double_rare",
    "1-star": "illustration_rare",
    "2-star": "special_art",
    "3-star": "immersive_rare",
    "crown": "crown_rare",
    "shiny-1": "shiny_rare",
    "shiny-2": "double_shiny_rare",
    "1-star shiny": "shiny_rare",
    "2-star shiny": "double_shiny_rare",
    "shiny 1": "shiny_rare",
    "shiny 2": "double_shiny_rare",
}

# Default generation for sets not yet classified.
_GENERATION_LOOKUP = {
    "A1": "G1",
    "A1a": "G1",
    "A2": "G1",
    "A2a": "G1",
    "A2b": "G2",
    "A3": "G2",
    "A3a": "G2",
    "A3b": "G2",
    "A4": "G2",
    "A4a": "G2",
    "A4b": "G3",
}
_DEFAULT_GENERATION = "G4"  # All B-series and any future sets


def _default_generation(set_code: str) -> str:
    return _GENERATION_LOOKUP.get(set_code, _DEFAULT_GENERATION)


class Command(BaseCommand):
    """Scrape pocket.pokemongohub.net and update CSV seed files."""

    help = "Scrape pocket.pokemongohub.net and update data/ CSV files"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "TCGPTracker-scraper/1.0 (educational data sync)",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self._page_cache: dict = {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        """Main command handler."""
        existing = self._load_existing_data()
        slugs, en_booster_slugs, de_set_slugs, de_booster_slugs = (
            self._collect_slugs_to_process(existing)
        )
        if not slugs:
            self.stdout.write(
                self.style.SUCCESS("All sets are up to date. Nothing to do.")
            )
            return

        new_data = self._scrape_set_pages(slugs, de_set_slugs, existing)
        pack_cards = self._scrape_booster_pages(
            en_booster_slugs, de_booster_slugs, new_data, existing
        )
        _assign_pack_membership(pack_cards, new_data["cards"])
        self._write_csv_files(new_data)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Added {len(new_data['sets'])} set(s), "
                f"{len(new_data['cards'])} card(s)."
            )
        )

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _load_existing_data(self) -> dict:
        """Read all five seed CSV files and return them in a single dict."""
        return {
            "sets": _read_csv_as_dict(DATA_DIR / "sets.csv", ("number",)),
            "cards": _read_csv_as_dict(
                DATA_DIR / "cards.csv", ("set_number", "number")
            ),
            "set_trans": _read_csv_as_dict(
                DATA_DIR / "set_translations.csv", ("english_name",)
            ),
            "pack_trans": _read_csv_as_dict(
                DATA_DIR / "pack_translations.csv",
                ("set_english_name", "pack_english_name"),
            ),
            "card_trans": _read_csv_as_dict(
                DATA_DIR / "card_translations.csv", ("card_english_name",)
            ),
        }

    def _collect_slugs_to_process(
        self, existing: dict
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        """
        Fetch homepage slug lists and decide which set slugs need scraping.

        Returns ``(set_slugs_to_process, en_booster_slugs, de_set_slugs,
        de_booster_slugs)``.
        """
        sets_with_cards = {k[0] for k in existing["cards"]}
        empty_set_codes = {
            code for code in existing["sets"] if code not in sets_with_cards
        }
        if empty_set_codes:
            self.stdout.write(
                "Found "
                + str(len(empty_set_codes))
                + " set(s) with no cards: "
                + ", ".join(sorted(empty_set_codes))
            )

        self.stdout.write("Collecting slugs from homepage…")
        en_set_slugs = [s for s in self._collect_slugs("en", "set") if not _is_promo(s)]
        en_booster_slugs = [
            s for s in self._collect_slugs("en", "booster") if not _is_promo(s)
        ]
        de_set_slugs = self._collect_slugs("de", "set")
        de_booster_slugs = self._collect_slugs("de", "booster")

        slug_to_code = {
            s: c for s in en_set_slugs if (c := _slug_to_set_code(s, existing["sets"]))
        }
        slugs_to_process = [
            s
            for s in en_set_slugs
            if slug_to_code.get(s) in empty_set_codes or s not in slug_to_code
        ]
        skipped = len(en_set_slugs) - len(slugs_to_process)
        if slugs_to_process:
            self.stdout.write(
                f"Processing {len(slugs_to_process)} set(s) "
                f"({skipped} already complete, skipped)."
            )
        return slugs_to_process, en_booster_slugs, de_set_slugs, de_booster_slugs

    def _scrape_set_pages(
        self,
        slugs: list[str],
        de_set_slugs: list[str],
        existing: dict,
    ) -> dict:
        """
        Scrape EN (and DE) set pages for *slugs*.

        Returns a ``new_data`` dict with keys ``sets``, ``cards``,
        ``set_trans``, ``pack_trans``, ``card_trans``, ``processing_codes``.
        """
        new_data: dict = {
            "sets": {},
            "cards": {},
            "set_trans": {},
            "pack_trans": {},
            "card_trans": {},
            "processing_codes": set(),
        }
        for slug in slugs:
            self.stdout.write(f"  Set: {slug}")
            en_data = self._parse_set_page(slug, "en")
            if en_data is None:
                continue
            de_slug = _find_matching_slug(slug, de_set_slugs)
            de_data = self._parse_set_page(de_slug, "de") if de_slug else None
            self._collect_set_data(en_data, de_data, existing, new_data)
        return new_data

    def _collect_set_data(
        self,
        en_data: dict,
        de_data: dict | None,
        existing: dict,
        new_data: dict,
    ) -> None:
        """Merge one set's scraped data into *new_data*."""
        set_code = en_data["set_code"]
        new_data["processing_codes"].add(set_code)

        if set_code not in existing["sets"]:
            new_data["sets"][set_code] = {
                "number": set_code,
                "name": en_data["name"],
                "release_date": en_data["release_date"],
                "generation": _default_generation(set_code),
            }

        canonical_name = _canonical_set_name(
            set_code, en_data["name"], existing, new_data
        )

        if canonical_name not in existing["set_trans"]:
            de_name = de_data["name"] if de_data else canonical_name
            new_data["set_trans"][canonical_name] = de_name

        for card in en_data["cards"]:
            key = (set_code, card["number"])
            if key not in existing["cards"]:
                new_data["cards"][key] = {
                    "set_number": set_code,
                    "number": card["number"],
                    "card": card["name"],
                    "pack": "",
                    "rarity": card["rarity"],
                }

        if de_data:
            en_by_num = {c["number"]: c["name"] for c in en_data["cards"]}
            for card in de_data["cards"]:
                en_name = en_by_num.get(card["number"])
                if (
                    en_name
                    and en_name != card["name"]
                    and en_name not in existing["card_trans"]
                ):
                    new_data["card_trans"][en_name] = card["name"]

    def _scrape_booster_pages(
        self,
        en_booster_slugs: list[str],
        de_booster_slugs: list[str],
        new_data: dict,
        existing: dict,
    ) -> dict:
        """
        Scrape booster pages for sets in ``new_data["processing_codes"]``.

        Returns ``pack_cards`` mapping ``(set_code, pack_name)`` → card numbers.
        """
        processing_codes = new_data["processing_codes"]
        all_sets = {**existing["sets"], **new_data["sets"]}

        slug_name_prefixes = _processing_slug_names(processing_codes, all_sets)
        booster_slugs = _filter_booster_slugs(en_booster_slugs, slug_name_prefixes)
        skipped = len(en_booster_slugs) - len(booster_slugs)
        self.stdout.write(
            f"Scraping {len(booster_slugs)} booster page(s) ({skipped} skipped)."
        )

        pack_cards: dict[tuple[str, str], set[str]] = {}
        for slug in booster_slugs:
            self.stdout.write(f"  Booster: {slug}")
            en_data = self._parse_booster_page(slug, "en")
            if en_data is None:
                continue
            set_code = _resolve_set_code(en_data["set_name"], all_sets)
            if not set_code:
                self.stdout.write(
                    self.style.WARNING(
                        f"    Cannot resolve set code for "
                        f"'{en_data['set_name']}', skipping"
                    )
                )
                continue
            if set_code not in processing_codes:
                continue
            pack_en = en_data["pack_name"]
            pack_cards[(set_code, pack_en)] = en_data["card_numbers"]
            de_slug = _find_matching_slug(slug, de_booster_slugs)
            de_data = self._parse_booster_page(de_slug, "de") if de_slug else None
            pack_de = de_data["pack_name"] if de_data else pack_en
            self._collect_pack_trans(set_code, pack_en, pack_de, (existing, new_data))
        return pack_cards

    def _collect_pack_trans(
        self,
        set_code: str,
        pack_en: str,
        pack_de: str,
        context: tuple[dict, dict],
    ) -> None:
        """Add a pack translation row to *new_data* if needed."""
        existing, new_data = context
        canonical_set_name = _canonical_set_name(set_code, pack_en, existing, new_data)
        set_has_trans = any(k[0] == canonical_set_name for k in existing["pack_trans"])
        if set_code not in new_data["sets"] and set_has_trans:
            return
        all_sets = {**existing["sets"], **new_data["sets"]}
        set_data = all_sets.get(set_code)
        set_name_for_csv = (
            set_data.get("name", canonical_set_name)
            if isinstance(set_data, dict)
            else canonical_set_name
        )
        new_data["pack_trans"][(set_code, pack_en)] = {
            "set_english_name": set_name_for_csv,
            "pack_english_name": pack_en,
            "pack_german_name": pack_de,
        }

    def _write_csv_files(self, new_data: dict) -> None:
        """Append all new rows to the seed CSV files."""
        self.stdout.write("Writing CSV files…")
        _append_csv(
            DATA_DIR / "sets.csv",
            ["number", "name", "release_date", "generation"],
            new_data["sets"].values(),
        )
        _append_csv(
            DATA_DIR / "cards.csv",
            ["set_number", "number", "card", "pack", "rarity"],
            new_data["cards"].values(),
        )
        _append_csv(
            DATA_DIR / "set_translations.csv",
            ["english_name", "german_name"],
            (
                {"english_name": k, "german_name": v}
                for k, v in new_data["set_trans"].items()
            ),
        )
        _append_csv(
            DATA_DIR / "pack_translations.csv",
            ["set_english_name", "pack_english_name", "pack_german_name"],
            new_data["pack_trans"].values(),
        )
        _append_csv(
            DATA_DIR / "card_translations.csv",
            ["card_english_name", "card_german_name"],
            (
                {"card_english_name": k, "card_german_name": v}
                for k, v in new_data["card_trans"].items()
            ),
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> BeautifulSoup:
        """Fetch *url* and return a BeautifulSoup object."""
        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()
        time.sleep(0.4)  # be polite
        return BeautifulSoup(resp.text, "lxml")

    def _get_next_data(self, soup: BeautifulSoup) -> dict | None:
        """Extract the embedded __NEXT_DATA__ JSON from a Next.js page."""
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                return json.loads(script.string)
            except json.JSONDecodeError:
                return None
        return None

    # ------------------------------------------------------------------
    # Homepage scraping
    # ------------------------------------------------------------------

    def _collect_slugs(self, lang: str, kind: str) -> list[str]:
        """
        Return deduplicated list of URL slugs for *kind* ('set' or 'booster')
        found on the homepage for *lang*.
        """
        soup = self._fetch(f"{BASE_URL}/{lang}")
        seen: dict[str, None] = {}  # ordered dedup via dict
        pattern = re.compile(rf"/{re.escape(lang)}/{re.escape(kind)}/([^/?#]+)")
        for a in soup.find_all("a", href=True):
            m = pattern.search(a["href"])
            if m:
                seen[m.group(1)] = None
        return list(seen)

    # ------------------------------------------------------------------
    # Set page scraping
    # ------------------------------------------------------------------

    def _parse_set_page(self, slug: str, lang: str) -> dict | None:
        """
        Parse a set detail page.

        Returns a dict with keys:
            set_code, name, release_date, cards (list of {number, name, rarity})
        or None on failure.
        """
        cache_key = (slug, lang)
        if cache_key in self._page_cache:
            return self._page_cache[cache_key]

        url = f"{BASE_URL}/{lang}/set/{slug}"
        try:
            soup = self._fetch(url)
        except requests.HTTPError as exc:
            self.stdout.write(self.style.WARNING(f"    HTTP error for {url}: {exc}"))
            self._page_cache[cache_key] = None
            return None

        # Try structured __NEXT_DATA__ first
        result = self._parse_set_from_next_data(soup, lang)
        if not result:
            # Fallback: parse HTML
            result = self._parse_set_from_html(soup, lang, slug)

        self._page_cache[cache_key] = result
        return result

    def _parse_set_from_next_data(self, soup: BeautifulSoup, lang: str) -> dict | None:
        """Try to extract set data from embedded __NEXT_DATA__ JSON."""
        data = self._get_next_data(soup)
        if not data:
            return None
        try:
            page_props = data["props"]["pageProps"]
            raw_set = (
                page_props.get("set")
                or page_props.get("setData")
                or page_props.get("data")
            )
            if not raw_set:
                return None

            set_code = (
                raw_set.get("id") or raw_set.get("setNumber") or raw_set.get("localId")
            )
            name = raw_set.get("name", "")
            release_date = _parse_date(raw_set.get("releaseDate", ""))

            raw_cards = raw_set.get("cards") or []
            cards = []
            for rc in raw_cards:
                card_num = str(rc.get("number") or rc.get("localId") or "").zfill(3)
                card_name = rc.get("name", "")
                rarity_raw = (rc.get("rarity") or "").lower().replace(" ", "-")
                rarity = _normalise_rarity(rarity_raw)
                if card_num and card_name:
                    cards.append(
                        {"number": card_num, "name": card_name, "rarity": rarity}
                    )

            if set_code and name and cards:
                return {
                    "set_code": set_code,
                    "name": name,
                    "release_date": release_date,
                    "cards": cards,
                }
        except (KeyError, TypeError, AttributeError):
            pass
        return None

    def _parse_set_from_html(
        self, soup: BeautifulSoup, lang: str, slug: str
    ) -> dict | None:
        """Parse set data by walking the HTML tree."""
        # ---- Set code from page title ----
        h1 = soup.find("h1")
        if not h1:
            return None
        title_text = h1.get_text(" ", strip=True)
        set_code = _extract_set_code(title_text)
        name = _extract_set_name_from_title(title_text)
        if not set_code:
            return None

        # ---- Release date from summary table ----
        release_date = ""
        for td in soup.find_all("td"):
            text = td.get_text(strip=True)
            if "/" in text and len(text) <= 12:
                release_date = _parse_date(text)
                if release_date:
                    break

        # ---- Cards grouped by rarity ----
        cards = self._extract_cards_by_rarity(soup, lang)
        return {
            "set_code": set_code,
            "name": name,
            "release_date": release_date,
            "cards": cards,
        }

    def _extract_cards_by_rarity(self, soup: BeautifulSoup, lang: str) -> list[dict]:
        """
        Parse cards grouped by rarity.

        The set page renders ALL cards once (no rarity) at the top, then again
        in per-rarity sections further down.  We wait for the first rarity
        heading before collecting any card links so we only pick up the
        rarity-grouped section.

        Falls back to section-id scanning if the headings approach finds nothing.
        """
        cards: dict[str, dict] = {}  # card_number → first occurrence wins
        current_rarity = ""
        seen_first_rarity_heading = False

        for el in soup.find_all(["h1", "h2", "h3", "h4", "a"]):
            if el.name in ("h1", "h2", "h3", "h4"):
                rarity = _rarity_from_heading(el.get_text(" ", strip=True).lower())
                if rarity:
                    current_rarity = rarity
                    seen_first_rarity_heading = True
            elif (
                el.name == "a"
                and seen_first_rarity_heading
                and f"/{lang}/card/" in el.get("href", "")
            ):
                num, name = _parse_card_anchor(el, lang)
                if num and name and num not in cards:
                    cards[num] = {"number": num, "name": name, "rarity": current_rarity}

        return sorted(cards.values(), key=lambda c: int(c["number"]))

    # ------------------------------------------------------------------
    # Booster page scraping
    # ------------------------------------------------------------------

    def _parse_booster_page(self, slug: str, lang: str) -> dict | None:
        """
        Parse a booster pack detail page.

        Returns a dict with keys:
            set_name, pack_name, card_numbers (set of zero-padded strings)
        or None on failure.
        """
        url = f"{BASE_URL}/{lang}/booster/{slug}"
        try:
            soup = self._fetch(url)
        except requests.HTTPError as exc:
            self.stdout.write(self.style.WARNING(f"    HTTP error for {url}: {exc}"))
            return None

        # ---- Title: "{Set}: {Pack} Booster Pack Card List" or similar ----
        h1 = soup.find("h1")
        if not h1:
            return None
        title = h1.get_text(" ", strip=True)
        set_name, pack_name = _parse_booster_title(title, lang)

        # ---- If set_name == pack_name (single-pack set), find the real set name
        #      from a breadcrumb/nav link pointing to a set page ----
        if set_name == pack_name:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if f"/{lang}/set/" in href:
                    link_text = a.get_text(" ", strip=True)
                    if link_text and link_text.lower() not in ("home", ""):
                        set_name = link_text
                        break

        # ---- Card numbers from links ----
        card_numbers: set[str] = set()
        for a in soup.find_all("a", href=True):
            if f"/{lang}/card/" not in a["href"]:
                continue
            num, _ = _parse_card_anchor(a, lang)
            if num:
                card_numbers.add(num)

        if not set_name or not card_numbers:
            return None

        return {
            "set_name": set_name,
            "pack_name": pack_name,
            "card_numbers": card_numbers,
        }


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def _canonical_set_name(
    set_code: str, fallback: str, existing: dict, new_data: dict
) -> str:
    """Return the canonical English set name for *set_code*."""
    if set_code in existing["sets"]:
        return existing["sets"][set_code].get("name", fallback)
    return new_data["sets"].get(set_code, {}).get("name", fallback)


def _processing_slug_names(processing_codes: set[str], all_sets: dict) -> set[str]:
    """Return kebab-slug names for the sets being processed this run."""
    result = set()
    for code in processing_codes:
        data = all_sets.get(code)
        name = data.get("name", "") if isinstance(data, dict) else ""
        if name:
            result.add(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    return result


def _assign_pack_membership(
    pack_cards: dict[tuple[str, str], set[str]], new_cards: dict
) -> None:
    """Set the ``pack`` field on each new card based on *pack_cards*."""
    for (set_code, pack_name), card_numbers in pack_cards.items():
        for num in card_numbers:
            row = new_cards.get((set_code, num))
            if row is None:
                continue
            existing_pack = row["pack"]
            if existing_pack:
                parts = existing_pack.split("|")
                if pack_name not in parts:
                    parts.append(pack_name)
                    row["pack"] = "|".join(sorted(parts))
            else:
                row["pack"] = pack_name


def _slug_to_set_code(slug: str, existing_sets: dict) -> str | None:
    """
    Map a homepage set URL slug to an existing set code without fetching the page.

    Slug format: ``{id}-{name}`` e.g. ``t3hb77i3xy08no0-genetic-apex``.
    The name part is compared against slugified set names from *existing_sets*.
    """
    dash_idx = slug.find("-")
    if dash_idx < 0:
        return None
    slug_name = slug[dash_idx + 1 :]  # e.g. "genetic-apex"

    for code, data in existing_sets.items():
        name = data.get("name", "") if isinstance(data, dict) else str(data)
        name_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if name_slug == slug_name:
            return code
    return None


def _filter_booster_slugs(
    booster_slugs: list[str], set_slug_names: set[str]
) -> list[str]:
    """
    Return only the booster slugs whose name part starts with one of the
    given *set_slug_names*.  Falls back to returning ALL slugs when
    *set_slug_names* is empty (nothing to filter against).

    For older sets (A-series) the booster slug is just the pack name with no
    set-name prefix (e.g. ``ao4yfttve01s9d3-mewtwo``).  Those slugs will NOT
    match any set_slug_name and are excluded — which is correct, since those
    sets are already complete.
    """
    if not set_slug_names:
        return booster_slugs
    result = []
    for slug in booster_slugs:
        dash_idx = slug.find("-")
        slug_name = slug[dash_idx + 1 :] if dash_idx >= 0 else slug
        if any(slug_name.startswith(s) for s in set_slug_names):
            result.append(slug)
    return result


def _is_promo(slug: str) -> bool:
    """Return True if the slug belongs to a promotional set."""
    return "promo" in slug.lower()


def _find_matching_slug(en_slug: str, de_slugs: list[str]) -> str | None:
    """
    Find the DE slug that corresponds to an EN slug.
    Slugs share the same ID prefix (e.g. 't3hb77i3xy08no0-genetic-apex').
    """
    prefix = en_slug.split("-")[0]
    for s in de_slugs:
        if s.startswith(prefix):
            return s
    return None


def _resolve_set_code(set_name: str, sets_dict: dict) -> str | None:
    """
    Given a set's English name, return its code from *sets_dict*.
    Tries exact match first, then case-insensitive prefix match.
    """
    needle = set_name.lower()
    best_code = None
    best_len = 0
    for code, data in sets_dict.items():
        if isinstance(data, dict):
            name = data.get("name", "")
        else:
            name = str(data)
        name_lower = name.lower()
        if name_lower == needle:
            return code  # exact match wins immediately
        # Prefix match: e.g. "Deluxe Pack" matches "Deluxe Pack ex"
        if name_lower.startswith(needle) and len(needle) > best_len:
            best_len = len(needle)
            best_code = code
    return best_code


def _read_csv_as_dict(path: Path, key_cols: tuple[str, ...]) -> dict:
    """
    Read a CSV file and return a dict keyed by the tuple of values in
    *key_cols*.  Single-key tuples are unwrapped to plain strings.
    """
    result = {}
    if not path.exists():
        return result
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key_vals = tuple(row[k] for k in key_cols)
            key = key_vals[0] if len(key_vals) == 1 else key_vals
            result[key] = row
    return result


def _append_csv(path: Path, fieldnames: list[str], rows) -> None:
    """Append *rows* to the CSV at *path* (file must already exist)."""
    rows = list(rows)
    if not rows:
        return
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Text / HTML parsing helpers
# ---------------------------------------------------------------------------


def _extract_set_code(title: str) -> str:
    """
    Extract set code like 'A1', 'B2a' from a title such as
    'Genetic Apex Full Card List (A1)'.
    """
    m = re.search(r"\(([A-Z][0-9]+[a-z]?)\)", title)
    return m.group(1) if m else ""


def _extract_set_name_from_title(title: str) -> str:
    """
    Strip trailing set-list suffix from a page title (any supported language).

    English: 'Genetic Apex Full Card List (A1)'
    German:  'Unschlagbare Gene vollständige Kartenliste (A1)'
    """
    name = re.sub(
        r"\s*(Full\s+Card\s+List|vollst[äa]ndige\s+Kartenliste)\s*\([^)]*\)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return name.strip()


def _parse_date(raw: str) -> str:
    """
    Convert a date string in M/D/YYYY, D.M.YYYY or YYYY-MM-DD formats to
    ISO YYYY-MM-DD.  Returns '' if the input cannot be parsed.
    """
    raw = raw.strip()
    # Already ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    # MM/DD/YYYY or M/D/YYYY (US format used on EN pages)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if m:
        month, day, year = m.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    # D.M.YYYY (used on some DE pages)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", raw)
    if m:
        day, month, year = m.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return ""


def _parse_card_anchor(a, lang: str) -> tuple[str, str]:
    """
    Extract (zero_padded_number, card_name) from a card <a> element.

    The site renders cards as anchor tags containing:
      - <img alt="CardName (Pokémon TCG Pocket)">  → card name
      - <small>#N</small>                          → card number
    """
    # Card name from img alt
    img = a.find("img", alt=True)
    if not img:
        return "", ""
    alt_text = img["alt"]
    name = alt_text.replace(" (Pok\u00e9mon TCG Pocket)", "").strip()
    if not name:
        return "", ""

    # Card number from <small> containing "#N"
    for small in a.find_all("small"):
        text = small.get_text(strip=True)
        m = re.search(r"#(\d+)$", text)
        if m:
            return m.group(1).zfill(3), name

    # Fallback: try extracting number from the href slug
    # href like "/en/card/abc123-bulbasaur" doesn’t contain the number; skip.
    return "", ""


def _rarity_from_heading(heading_lower: str) -> str:
    """
    Map a lower-cased heading string to an internal rarity name.
    Checks longer (more specific) keywords first to avoid false prefix matches
    (e.g. '1-star shiny' before '1-star').
    Returns '' if the heading is not a rarity section header.
    """
    for keyword, rarity in sorted(
        RARITY_HEADING_MAP.items(), key=lambda kv: -len(kv[0])
    ):
        if keyword in heading_lower:
            return rarity
    return ""


def _normalise_rarity(raw: str) -> str:
    """Map a raw rarity string from the API/page to an internal name."""
    raw = raw.lower().strip()
    # Direct map
    if raw in RARITY_HEADING_MAP:
        return RARITY_HEADING_MAP[raw]
    # Partial match
    for key, value in RARITY_HEADING_MAP.items():
        if key in raw:
            return value
    return raw


def _parse_booster_title(title: str, lang: str) -> tuple[str, str]:
    """
    Extract (set_name, pack_name) from a booster page title.

    English examples:
        'Genetic Apex: Mewtwo Booster Pack Card List'  → ('Genetic Apex', 'Mewtwo')
        'Paldean Wonders Booster Pack Card List'        → ('Paldean Wonders', 'Paldean Wonders')

    German examples:
        'Unschlagbare Gene: Mewtu Booster-Pack Kartenliste' → ('Unschlagbare Gene', 'Mewtu')
        'Wundervolles Paldea Booster-Pack Kartenliste'      → ('Wundervolles Paldea', 'Wundervolles Paldea')
    """
    # Strip trailing booster-pack suffix in any supported language.
    # Handles: "Booster Pack Card List" (EN)
    #          "Booster-Pack Kartenliste" (DE with separator)
    #          "Boosterpack-Kartenliste" (DE compound word)
    cleaned = re.sub(
        r"\s*Booster[\s\-]?Pack[\s\-]?(Card\s+List|Kartenliste)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    if ":" in cleaned:
        set_part, pack_part = cleaned.split(":", 1)
        return set_part.strip(), pack_part.strip()

    # No colon → single-pack set; pack name equals set name
    return cleaned, cleaned

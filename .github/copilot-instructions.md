# Project Guidelines

## Overview

TCGPTracker is a Django 5.2 / Python 3.13 web app for tracking Pokémon TCG Pocket card collections. See `README.md` for full setup instructions.

## Architecture

- **`apps/tracker/`** — single Django app containing all domain logic
  - `models/cards.py` — `Generation`, `PackType`, `PokemonSet`, `Pack`, `Card`, `Rarity`, `RarityProbability`
  - `models/users.py` — `UserCard`, `UserProfile`, `FriendRequest`
  - `views/` — split by domain: `cards.py`, `friends.py`, `users.py`, `health.py`
  - `management/commands/` — `import_data`, `sync_tcgdex`, `update_pack_generations`, `validate_probabilities`
  - `utils.py` — standalone utility/helper functions
  - `services/` — shared business logic that is not a model or view (create the directory if absent)
- **`tcgptracker/settings/`** — layered settings: `base.py` → `development.py` / `production.py`
- **`data/`** — canonical CSV seed files used by `import_data`

## Code Style

- Formatter: **Black** (default line length 88)
- Import order: **isort** with `profile = "black"`
- HTML templates: **djlint**
- All source files use module-level docstrings and function-level docstrings ("""...""")
- Views are function-based and decorated with `@login_required` where auth is required

## Conventions

- New models belong in `apps/tracker/models/cards.py` if they primarily represent TCG domain objects (cards, sets, rarities, packs); they belong in `models/users.py` if they primarily represent user state, relationships, or preferences. Models with mixed concerns go in `models/users.py`. Export all new models via `models/__init__.py`
- Shared business logic that is not a model or view belongs in `apps/tracker/services/` (create the directory if absent). Standalone utility functions belong in `apps/tracker/utils.py`
- New views belong in the relevant file under `apps/tracker/views/`; register routes in `apps/tracker/urls.py`
- Use `get_object_or_404` and `@login_required` consistently in views
- Translatable strings use `gettext_lazy as _`; run `makemessages` after adding new strings
- Migrations are committed; always run `makemigrations` after model changes. Verify that exactly one new migration file is created containing only the expected schema changes. If `makemigrations` reports "No changes detected", confirm the new model is exported in `models/__init__.py` and the app is listed in `INSTALLED_APPS`

## Build and Test

Tests live in `apps/tracker/tests/` (e.g., `apps/tracker/tests/test_models_cards.py`). Use `pytest-django` fixtures; do not use Django's `TestCase` class.

```bash
# Install deps
poetry install

# Run tests
poetry run pytest

# Apply migrations (dev)
DJANGO_SETTINGS_MODULE=tcgptracker.settings.development python manage.py migrate

# Compile translations
python manage.py compilemessages
```

## Database

- Development: SQLite at `tcgptracker/db.dev.sqlite3`
- Production: PostgreSQL via `DATABASE_URL` env var (psycopg 3)

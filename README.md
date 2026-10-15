# TCGPTracker

A Django-based web app for tracking your Pokémon TCG Pocket card collection. Browse sets, mark cards as collected, track your pack-opening progress, and connect with friends.

## Features

- Track collected cards across all Pokémon TCG Pocket sets
- View pull probabilities per rarity and pack type (including God Packs)
- Search cards by name with multilingual support (English / German)
- Friend system with friend codes and friend requests
- Progressive Web App (PWA) support
- Admin interface with CSV data import

## Tech Stack

- **Backend:** Django 5.2, Python 3.13
- **Database:** PostgreSQL (production) / SQLite (development)
- **Cache/Sessions:** Redis (production) / locmem + DB sessions (development)
- **Frontend:** Bootstrap, django-widget-tweaks
- **Server:** Gunicorn + WhiteNoise
- **Containerisation:** Docker & Docker Compose

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

### Local development (SQLite)

```bash
# Install dependencies
uv sync

# Apply migrations
DJANGO_SETTINGS_MODULE=tcgptracker.settings.development uv run python manage.py migrate

# Import seed data
DJANGO_SETTINGS_MODULE=tcgptracker.settings.development uv run python manage.py import_data \
  --sets data/sets.csv \
  --cards data/cards.csv \
  --rarities data/rarities.csv \
  --packtypes data/pack_types.csv

# Start the development server
DJANGO_SETTINGS_MODULE=tcgptracker.settings.development uv run python manage.py runserver
```

Open <http://localhost:8000>.

### Docker (PostgreSQL)

Create a `.env` file in the project root:

```env
DJANGO_SETTINGS_MODULE=tcgptracker.settings.production
SECRET_KEY=your-secret-key
DATABASE_URL=postgres://tcgpuser:secret@db:5432/tcgp
ALLOWED_HOSTS=localhost
REDIS_URL=redis://:password@your-redis-host:6379/1
S3_ENDPOINT=http://minio:9000
S3_BUCKET=tcgptracker-images
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

The `S3_*` variables are optional. When `S3_ENDPOINT` is set, card thumbnails
and set logos are read from that S3-compatible bucket (MinIO) and served
through the app's `/images/` proxy, so the bucket can stay private.
`S3_REGION` defaults to `eu-central-1`. Fill the bucket with
`manage.py sync_card_images`, and re-run it after new sets are imported. When
`S3_ENDPOINT` is unset, no images are shown.

`REDIS_URL` is optional. When set, it enables the Redis cache backend and
Redis-backed sessions (`cached_db`, so sessions survive a Redis restart). When
unset, the app falls back to an in-process cache and DB-backed sessions.

Then start the stack:

```bash
docker compose up --build
```

## Running Tests

```bash
uv run pytest
```

## Management Commands

| Command | Description |
|---|---|
| `import_data` | Import sets, cards, rarities and pack types from CSV files |
| `sync_tcgdex` | Sync card data from the TCGdex API |
| `sync_flibustier` | Sync new sets/cards from the flibustier JSON dataset into `data/*.csv` |
| `sync_card_images` | Upload missing card thumbnails and set logos to the image bucket |
| `update_pack_generations` | Backfill generation data on packs |
| `validate_probabilities` | Validate that rarity probabilities sum to 1 per pack slot |

## Project Structure

```
apps/tracker/          # Main Django app
  models/              # cards.py, users.py
  views/               # cards.py, friends.py, users.py, health.py
  templates/tracker/   # HTML templates
  management/commands/ # Custom management commands
  migrations/          # Database migrations
data/                  # Seed CSV files
tcgptracker/           # Django project config & settings
```

## Localisation

Translations live in `apps/tracker/locale/` and `tcgptracker/locale/`. To compile messages:

```bash
uv run python manage.py compilemessages
```

To find missing translation strings:

```bash
python find_missing_translations.py
```

## License

MIT

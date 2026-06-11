# Paris Flash ⚡

Hyper-fast static event aggregator for Paris. Find what to do in under 3 seconds.

## How it works

1. **`src/scraper.py`** — fetches a handful of Parisian "what to do" pages, strips
   them down to readable text + links with BeautifulSoup, and asks Mistral AI
   (structured JSON outputs) to extract a normalized list of events. Writes
   `data/events.json`.
2. **`src/build.py`** — injects `data/events.json` into `templates/index.html`
   and writes the final static site to `dist/index.html`.
3. **`.github/workflows/deploy.yml`** — runs both steps on a daily schedule
   and on every push to `main`, then deploys `dist/` to GitHub Pages.

No backend, no database — just a static HTML file refreshed on a schedule.

## Local setup

```bash
# Install dependencies
uv sync

# Set your Mistral API key
cp .env.example .env
# edit .env and fill in MISTRAL_API_KEY

# Run the pipeline
export $(cat .env | xargs)
uv run src/scraper.py   # -> data/events.json
uv run src/build.py     # -> dist/index.html
```

Open `dist/index.html` in a browser, or serve it locally:

```bash
python3 -m http.server 8000 --directory dist
```

## Data schema

Every event in `data/events.json` has exactly these fields:

| Field         | Description                                              |
| ------------- | --------------------------------------------------------- |
| `date`        | Readable date (e.g. "Mardi 9 Juin")                        |
| `lieu`        | Venue + arrondissement (e.g. "Le Hasard Ludique, 18e")     |
| `prix`        | Free-text price (e.g. "Gratuit", "12€")                    |
| `description` | One short sentence describing the event                   |
| `lien`        | Direct link to the event source                            |
| `categorie`   | One of: Soirées, Bouffe, Culture, Sport, Loisir, Concert / cinéma |

## Deployment

GitHub Pages, served from the `dist/` artifact built by the GitHub Actions
workflow. Set the `MISTRAL_API_KEY` repository secret, then enable Pages with
source "GitHub Actions" in the repo settings.

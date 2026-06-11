"""Compile templates/index.html + data/events.json into dist/index.html."""

from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT_DIR / "templates" / "index.html"
DATA_PATH = ROOT_DIR / "data" / "events.json"
DIST_DIR = ROOT_DIR / "dist"
OUTPUT_PATH = DIST_DIR / "index.html"

PLACEHOLDER = "__EVENTS_JSON__"


def main() -> None:
    if not DATA_PATH.exists():
        raise SystemExit(f"Missing {DATA_PATH}. Run `uv run src/scraper.py` first.")

    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"Missing template {TEMPLATE_PATH}.")

    events = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    events_json = json.dumps(events, ensure_ascii=False)
    # Avoid a stray "</script>" inside the JSON breaking out of the inline tag.
    events_json = events_json.replace("</", "<\\/")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"Placeholder {PLACEHOLDER!r} not found in {TEMPLATE_PATH}.")

    html = template.replace(PLACEHOLDER, events_json)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Built {OUTPUT_PATH.relative_to(ROOT_DIR)} with {len(events)} event(s).")


if __name__ == "__main__":
    main()

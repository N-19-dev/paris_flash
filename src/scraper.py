"""Paris Flash scraper.

Fetches raw HTML from a handful of Parisian "what to do" sources, strips it
down to readable text + links, and asks Mistral AI to extract a normalized
list of events matching our strict schema (see models.py).

Output: data/events.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from mistralai.client import Mistral
from mistralai.extra import response_format_from_pydantic_model

from models import Event, EventList

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT_DIR / "data" / "events.json"

MODEL = os.environ.get("MISTRAL_MODEL", "mistral-large-latest")

SOURCES: list[str] = [
    "https://www.sortiraparis.com/actualites/a-paris/guides/53380-que-faire-cette-semaine-du-8-au-14-juin-2026-vos-sorties-pour-une-semaine-remplie-a-paris",
    "https://parissecret.com/top-nouveautes/",
    "https://www.timeout.fr/paris/que-faire-a-paris/calendrier-mois?utm_source=chatgpt.com",
    "https://www.parisbouge.com",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

MAX_TEXT_CHARS = 12_000
MAX_LINKS = 60

SYSTEM_PROMPT = f"""Tu es un assistant qui extrait des événements (sorties, soirées, expos, concerts, activités) à Paris à partir du contenu brut d'une page web.

On te fournit :
- la date du jour (pour déduire les années manquantes)
- l'URL source de la page
- le texte visible de la page
- une liste de liens présents sur la page (texte du lien -> URL)

Pour CHAQUE événement distinct et concret que tu identifies, produis un objet JSON avec EXACTEMENT ces champs :

- "titre": titre court et accrocheur de l'événement lui-même (ex: "Concert David Guetta", "Expo Impressionnistes Méconnus"), DISTINCT du nom du lieu qui l'accueille.
- "date": format court et lisible en français (ex: "Mardi 9 Juin", "Du 12 au 15 juin", "Tous les week-ends de juin"). Si aucune date précise n'est donnée, écris "Date non précisée".
- "date_debut": date de DÉBUT au format ISO "AAAA-MM-JJ", déduite de "date" et de la date du jour fournie (ex: "Mardi 9 Juin" -> "2026-06-09"). Pour un événement récurrent ou étalé sur une période (ex: "Tous les vendredis de juin", "Du 12 au 15 juin"), utilise le premier jour de la période. Si la date est totalement inconnue, utilise la date du jour fournie.
- "date_fin": date de FIN au format ISO "AAAA-MM-JJ", ou null si l'événement n'a lieu qu'un seul jour. Pour une période ou un événement récurrent, utilise le dernier jour de la période.
- "lieu": nom du lieu + arrondissement si connu (ex: "Le Hasard Ludique, 18e"). Si l'arrondissement est inconnu, indique juste le nom du lieu, ou "Paris" si rien n'est précisé.
- "prix": texte libre et court (ex: "Gratuit", "12€", "Entrée libre", "À partir de 15€"). Si inconnu, écris "Non précisé".
- "description": UNE SEULE phrase courte (15 mots maximum) qui explique le concept de l'événement, sans superlatifs ni formules marketing.
- "description_longue": 2 à 4 phrases qui détaillent en quoi consiste l'événement (déroulement, ambiance, ce que les visiteurs peuvent y faire/voir), sans superlatifs ni formules marketing. Si peu d'informations sont disponibles, reformule la description courte de façon plus détaillée plutôt que d'inventer des détails.
- "accroche": 1 à 2 phrases avec un ton enthousiaste et promotionnel, écrites pour servir de légende à un post Instagram (peuvent inclure superlatifs, emojis et formulations marketing, contrairement à "description" et "description_longue").
- "lien": cherche activement dans la liste de liens fournis celui qui correspond le PLUS PRÉCISÉMENT à cet événement (le texte du lien mentionne le lieu, le titre ou l'activité de l'événement). Utilise cette URL en priorité, même si elle ne correspond pas exactement à l'URL source. Réutilise l'URL source telle quelle UNIQUEMENT si aucun lien plus spécifique n'existe dans la liste fournie.
- "lien_billetterie": si l'événement nécessite une réservation ou l'achat d'un billet ET qu'un lien de billetterie/réservation distinct figure dans les liens fournis, indique cette URL. Sinon, mets null (NE PAS réutiliser "lien" ni inventer une URL).
- "categorie": choisis EXACTEMENT une valeur parmi : "Soirées", "Bouffe", "Culture", "Sport", "Loisir", "Concert / cinéma".

Règles strictes :
- Ignore tout ce qui n'est pas un événement concret (publicités, menus de navigation, liens de réseaux sociaux, newsletters, articles génériques sans activité précise).
- N'invente aucune information : utilise les valeurs par défaut indiquées ci-dessus si une info est manquante.
- Maximum 12 événements, les plus pertinents et les plus concrets.
- Réponds uniquement en français, avec le JSON demandé."""


def fetch_page(url: str) -> tuple[str, list[tuple[str, str]]]:
    """Fetch a URL and return (cleaned visible text, list of (link text, href))."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "iframe"]):
        tag.decompose()

    text_lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    text = "\n".join(line for line in text_lines if line)
    text = text[:MAX_TEXT_CHARS]

    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        link_text = a.get_text(" ", strip=True)
        if not link_text or len(link_text) < 4:
            continue
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append((link_text[:80], absolute))
        if len(links) >= MAX_LINKS:
            break

    return text, links


def extract_events(client: Mistral, source_url: str, text: str, links: list[tuple[str, str]]) -> list[Event]:
    links_block = "\n".join(f"- {label} -> {href}" for label, href in links)
    user_content = (
        f"Date du jour : {date.today().isoformat()}\n\n"
        f"URL source : {source_url}\n\n"
        f"=== TEXTE DE LA PAGE ===\n{text}\n\n"
        f"=== LIENS DISPONIBLES ===\n{links_block}"
    )

    response_format = response_format_from_pydantic_model(EventList)

    res = client.chat.complete(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format=response_format,
        temperature=0.2,
    )

    content = res.choices[0].message.content
    if isinstance(content, list):
        content = "".join(chunk.text for chunk in content if hasattr(chunk, "text"))

    data = json.loads(content)
    parsed = EventList.model_validate(data)

    for event in parsed.events:
        if not event.lien.startswith("http"):
            event.lien = source_url

    return parsed.events


def main() -> None:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("ERROR: MISTRAL_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = Mistral(api_key=api_key)

    all_events: list[Event] = []

    for url in SOURCES:
        print(f"-> Fetching {url}")
        try:
            text, links = fetch_page(url)
        except requests.RequestException as exc:
            print(f"   WARN: could not fetch page ({exc})", file=sys.stderr)
            continue

        try:
            events = extract_events(client, url, text, links)
        except Exception as exc:  # noqa: BLE001 - keep pipeline alive on per-source failures
            print(f"   WARN: Mistral extraction failed ({exc})", file=sys.stderr)
            continue

        print(f"   -> {len(events)} event(s) extracted")
        all_events.extend(events)

        # Be polite with the source servers and the API rate limits.
        time.sleep(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps([event.model_dump() for event in all_events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {len(all_events)} event(s) to {OUTPUT_PATH.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()

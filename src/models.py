"""Shared data schema for Paris Flash events."""

from typing import Literal, Optional

from pydantic import BaseModel

CATEGORIES: list[str] = [
    "Soirées",
    "Bouffe",
    "Culture",
    "Sport",
    "Loisir",
    "Concert / cinéma",
]

Categorie = Literal[
    "Soirées",
    "Bouffe",
    "Culture",
    "Sport",
    "Loisir",
    "Concert / cinéma",
]


class Event(BaseModel):
    """A single Paris event - minimalist schema, strictly enforced."""

    model_config = {"extra": "forbid"}

    date: str
    date_debut: str
    date_fin: Optional[str]
    lieu: str
    prix: str
    description: str
    lien: str
    categorie: Categorie


class EventList(BaseModel):
    model_config = {"extra": "forbid"}

    events: list[Event]

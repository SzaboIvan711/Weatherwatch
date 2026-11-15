"""Supported locations.

A fixed allow-list instead of free-text geocoding: the API never forwards user
input to the upstream service, the set of cache keys and metric labels stays
small and bounded, and tests are deterministic. See ADR 0002.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Location:
    slug: str
    name: str
    latitude: float
    longitude: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


LOCATIONS: dict[str, Location] = {
    loc.slug: loc
    for loc in (
        Location("chur", "Chur", 46.8499, 9.5329),
        Location("davos", "Davos", 46.8043, 9.8372),
        Location("st-moritz", "St. Moritz", 46.4908, 9.8355),
        Location("zuerich", "Zürich", 47.3769, 8.5417),
        Location("bern", "Bern", 46.9481, 7.4474),
        Location("basel", "Basel", 47.5596, 7.5886),
        Location("lugano", "Lugano", 46.0037, 8.9511),
    )
}


class UnknownLocationError(LookupError):
    """Raised when a client asks for a location that is not on the allow-list."""

    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug


def resolve(slug: str | None, default: str) -> Location:
    key = (slug or default).strip().lower()
    try:
        return LOCATIONS[key]
    except KeyError:
        raise UnknownLocationError(key) from None

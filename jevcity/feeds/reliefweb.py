"""ReliefWeb disasters feed (free, no API key). Situational context, NOT incidents.

Returns `FeedAdvisory` records for the dashboard context strip. It never emits an
EventEnvelope — a disaster listing is not a triageable incident in this system,
and inventing one would misrepresent the data. Surfaced via FeedsResponse.advisories.
"""
from __future__ import annotations

from datetime import datetime

from jevcity.schemas import FeedAdvisory

from .base import FeedError

URL = (
    "https://api.reliefweb.int/v2/disasters"
    "?appname=jevcity-peshawar"
    "&filter[field][0]=country&filter[value][0]=Pakistan"
    "&limit=5&fields[include][]=name&fields[include][]=url"
    "&fields[include][]=date&sort[]=date:desc"
)


class ReliefWebFeed:
    name = "reliefweb"

    def __init__(self, client) -> None:
        self._client = client
        self.advisories: list[FeedAdvisory] = []

    def poll(self) -> list[object]:
        try:
            resp = self._client.get(URL)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise FeedError(f"reliefweb: {exc}") from exc
        rows = payload.get("data") or []
        out: list[FeedAdvisory] = []
        for row in rows:
            fields = row.get("fields") or {}
            title = fields.get("name") or "untitled advisory"
            url = None
            url_field = fields.get("url")
            if isinstance(url_field, dict):
                url = url_field.get("url")
            elif isinstance(url_field, str):
                url = url_field
            published = None
            date_field = fields.get("date")
            if isinstance(date_field, dict) and date_field.get("created"):
                try:
                    published = datetime.fromisoformat(
                        str(date_field["created"]).replace("Z", "+00:00")
                    )
                except ValueError:
                    published = None
            out.append(FeedAdvisory(title=title, url=url, published=published))
        self.advisories = out
        return out

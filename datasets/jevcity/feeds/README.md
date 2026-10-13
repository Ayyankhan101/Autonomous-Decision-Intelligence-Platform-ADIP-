# Recorded feed fixtures (workstream B4)

Network-free CI fixtures for `JEVCITY_FEED_MODE=live` tests. Record once against
live endpoints, commit, replay via `JEVCITY_FEED_RECORD=0` (default).

Files:
- `open-meteo.json` — weather snapshot response
- `usgs-seismic.json` — USGS 2.5-day GeoJSON (Peshawar bbox)
- `gdacs.json` — GDACS disaster feed
- `reliefweb.json` — ReliefWeb Pakistan disaster list

Re-record: `JEVCITY_FEED_RECORD=1 uv run pytest tests/jevcity/test_feeds_e2e.py -q`

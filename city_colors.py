"""Stable presentation-only city identities for the Europe trip.

Airport aliases identify the city they serve in this itinerary. Shannon is the
Galway gateway; home and unknown endpoints keep the navy base. No trip data is
modified and list order never determines a destination's color.
"""
import re

CITY_ALIASES = {
    'dublin': ('dublin', 'dub', 'dublin airport'),
    'galway': ('galway', 'shannon', 'snn', 'shannon airport'),
    'edinburgh': ('edinburgh', 'edi', 'edinburgh airport'),
    'inverness': ('inverness', 'inv', 'inverness airport', 'glasgow', 'gla'),
    'london': ('london', 'lon', 'lhr', 'lgw', 'lcy', 'stn', 'ltn', 'heathrow', 'gatwick', 'london heathrow', 'london gatwick'),
    'home': ('stl', 'st louis', 'st. louis', 'saint louis'),
}
ALIASES = {alias: key for key, aliases in CITY_ALIASES.items() for alias in aliases}


def city_color(value):
    """Return a CSS identity, never arbitrary user text or a positional color."""
    normalized = ' '.join(str(value or '').strip().casefold().split())
    return ALIASES.get(normalized, 'neutral')


def _mentioned_city(value, last=False):
    """Read an endpoint embedded in a descriptive ground-transfer label."""
    text = str(value or '').casefold()
    matches = []
    for alias, key in ALIASES.items():
        for match in re.finditer(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text):
            matches.append((match.start(), len(alias), key))
    if not matches:
        return 'neutral'
    # Long aliases win ties (e.g. London Heathrow), with travel direction kept.
    if last:
        return max(matches, key=lambda m: (m[0], m[1]))[2]
    return min(matches, key=lambda m: (m[0], -m[1]))[2]


def route_colors(label='', origin='', destination='', fallback=''):
    """Return origin/destination identities without confusing layovers with endpoints."""
    if origin or destination:
        return city_color(origin), city_color(destination)
    for text in (label, fallback):
        parts = re.split(r'\s*(?:→|->|↔|\bto\b)\s*', str(text or ''), flags=re.I)
        if len(parts) >= 2:
            start = _mentioned_city(parts[0], last=True)
            end = _mentioned_city(parts[-1])
            if start != 'neutral' or end != 'neutral':
                return start, end
    single = city_color(label)
    return single, single

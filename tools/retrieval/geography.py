"""Where an item takes place: a full, readable location, its country, its continent.

Only conferences carry a place. The collector fills ``city``, ``country_code`` and
``country`` for some records and only a free-text ``place_text`` for the rest
("Ann Arbor, MI", "Brescia (Italy)", "Royal Agricultural University (RAU),
Cirencester, UK."); for some, ``city`` even holds a venue name. :func:`place_for`
reads all of it and returns the richest honest location, the country it names, and
that country's continent. Grants and fellowships have no place and get nothing.

The country is read, never guessed: a structured code first, then the place text's
last parts. A bare city ("Pittsburgh") or an unknown spelling gets no country and so
no continent. One heuristic is deliberate: a final two-letter part after a city
("Austin, TX") is read as a US state when it is one, since that is how US venues are
written; otherwise as an ISO country code ("Lisbon, PT").

The web app's conference filter keeps its own continent table (``continentOf`` in
``web/app/src/components/portal/sections/conference-filters.tsx``) with the same six
continent names, so a filter means the same on both surfaces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CONTINENTS = (
    "North America",
    "South America",
    "Europe",
    "Asia",
    "Africa",
    "Oceania",
)
#: A conference held only online.
ONLINE = "Online"

#: ISO alpha-2 → (country name, continent).
COUNTRIES: dict[str, tuple[str, str]] = {}
for _continent, _rows in {
    "North America": (
        "US United States|CA Canada|MX Mexico|CR Costa Rica|PA Panama|CU Cuba|"
        "JM Jamaica|DO Dominican Republic|GT Guatemala|HN Honduras|SV El Salvador|"
        "NI Nicaragua|BS Bahamas|BB Barbados|TT Trinidad and Tobago|PR Puerto Rico|"
        "BZ Belize|HT Haiti|GL Greenland|BM Bermuda"
    ),
    "South America": (
        "AR Argentina|BR Brazil|CL Chile|CO Colombia|PE Peru|UY Uruguay|"
        "VE Venezuela|EC Ecuador|BO Bolivia|PY Paraguay|GY Guyana|SR Suriname"
    ),
    "Europe": (
        "GB United Kingdom|IE Ireland|FR France|DE Germany|ES Spain|PT Portugal|"
        "IT Italy|NL Netherlands|BE Belgium|LU Luxembourg|CH Switzerland|AT Austria|"
        "SE Sweden|NO Norway|DK Denmark|FI Finland|IS Iceland|PL Poland|"
        "CZ Czech Republic|SK Slovakia|HU Hungary|GR Greece|RO Romania|BG Bulgaria|"
        "HR Croatia|RS Serbia|SI Slovenia|EE Estonia|LV Latvia|LT Lithuania|"
        "UA Ukraine|RU Russia|BY Belarus|MD Moldova|TR Turkey|CY Cyprus|MT Malta|"
        "AL Albania|BA Bosnia and Herzegovina|ME Montenegro|MK North Macedonia|"
        "XK Kosovo|LI Liechtenstein|MC Monaco|SM San Marino|AD Andorra|"
        "VA Vatican City|GI Gibraltar|FO Faroe Islands|AM Armenia|AZ Azerbaijan"
    ),
    "Asia": (
        "CN China|JP Japan|KR South Korea|KP North Korea|IN India|SG Singapore|"
        "MY Malaysia|ID Indonesia|TH Thailand|VN Vietnam|PH Philippines|TW Taiwan|"
        "HK Hong Kong|MO Macau|PK Pakistan|BD Bangladesh|LK Sri Lanka|NP Nepal|"
        "BT Bhutan|MV Maldives|MM Myanmar|KH Cambodia|LA Laos|BN Brunei|"
        "AE United Arab Emirates|SA Saudi Arabia|QA Qatar|IL Israel|JO Jordan|"
        "LB Lebanon|IR Iran|IQ Iraq|KW Kuwait|BH Bahrain|OM Oman|YE Yemen|SY Syria|"
        "PS Palestine|KZ Kazakhstan|UZ Uzbekistan|KG Kyrgyzstan|TJ Tajikistan|"
        "TM Turkmenistan|MN Mongolia|AF Afghanistan"
    ),
    "Africa": (
        "ZA South Africa|EG Egypt|MA Morocco|DZ Algeria|TN Tunisia|LY Libya|"
        "NG Nigeria|GH Ghana|KE Kenya|ET Ethiopia|TZ Tanzania|UG Uganda|RW Rwanda|"
        "SN Senegal|CI Ivory Coast|CM Cameroon|ZW Zimbabwe|ZM Zambia|"
        "MZ Mozambique|AO Angola|NA Namibia|BW Botswana|MU Mauritius|"
        "MG Madagascar|SD Sudan|BJ Benin|BF Burkina Faso|ML Mali|NE Niger|TG Togo|"
        "GA Gabon|CG Congo|CD Democratic Republic of the Congo|MW Malawi|"
        "SL Sierra Leone|LR Liberia|GM Gambia|GN Guinea|ER Eritrea|DJ Djibouti|"
        "SO Somalia|SC Seychelles|CV Cape Verde"
    ),
    "Oceania": (
        "AU Australia|NZ New Zealand|FJ Fiji|PG Papua New Guinea|WS Samoa|TO Tonga|"
        "VU Vanuatu|SB Solomon Islands|NC New Caledonia|PF French Polynesia"
    ),
}.items():
    for _row in _rows.split("|"):
        _code, _name = _row.split(" ", 1)
        COUNTRIES[_code] = (_name, _continent)

#: Other ways a country is written, lower-cased, → ISO code.
_ALIASES = {
    "usa": "US",
    "u.s.a": "US",
    "u.s": "US",
    "us": "US",
    "united states of america": "US",
    "united state": "US",
    "america": "US",
    "uk": "GB",
    "u.k": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "the netherlands": "NL",
    "holland": "NL",
    "korea": "KR",
    "republic of korea": "KR",
    "korea, republic of": "KR",
    "türkiye": "TR",
    "turkiye": "TR",
    "czechia": "CZ",
    "russian federation": "RU",
    "viet nam": "VN",
    "uae": "AE",
    "brasil": "BR",
    "macau sar": "MO",
    "macao": "MO",
    "hong kong sar": "HK",
    "côte d'ivoire": "CI",
    "cote d'ivoire": "CI",
    "p.r. china": "CN",
    "pr china": "CN",
    "people's republic of china": "CN",
}
_BY_NAME = {name.lower(): code for code, (name, _c) in COUNTRIES.items()} | _ALIASES

_US_STATES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
#: "Georgia" is a US state and a country, so on its own it names neither; "New York"
#: and "Washington" are read as the state (the city is in the US either way).
_STATE_NAMES = {
    name.lower(): name for name in _US_STATES.values() if name not in ("Georgia",)
} | {
    "d.c": "District of Columbia",
    "washington d.c": "District of Columbia",
    "washington dc": "District of Columbia",
}
_CA_PROVINCES = {
    "ontario",
    "quebec",
    "québec",
    "british columbia",
    "alberta",
    "manitoba",
    "saskatchewan",
    "nova scotia",
    "new brunswick",
    "newfoundland and labrador",
    "prince edward island",
    "on",
    "qc",
    "bc",
    "ab",
}
_ONLINE_WORDS = {"online", "virtual", "zoom", "teams", "virtual event", "webinar"}
_PLACEHOLDERS = {"", "unknown", "tbd", "tba", "n/a", "na", "none"}
_ZIP_STATE = re.compile(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b")


@dataclass(frozen=True)
class Place:
    display: str = ""
    country: str = ""  # full country name
    continent: str = ""  # one of CONTINENTS, ONLINE, or ""


def continent_for(country_code: str = "", country: str = "") -> str:
    """The continent of a country given by ISO alpha-2 code or by name; ``""``
    when neither is recognised (never a guess)."""
    code = _code(country_code) or _code_for_name(country)
    return COUNTRIES[code][1] if code else ""


def place_for(metadata: dict | None) -> Place:
    """The full location, country and continent of a conference record."""
    meta = metadata or {}
    city = _clean(meta.get("city"))
    text = _clean(meta.get("place_text"))
    if text.lower() in _PLACEHOLDERS:
        text = ""
    code = _code(meta.get("country_code")) or _code_for_name(
        _clean(meta.get("country"))
    )
    state = ""
    if not code and text:
        code, state = _read_tail(text)
    country = COUNTRIES[code][0] if code else ""

    online_only = bool(meta.get("is_virtual")) and not meta.get("is_hybrid")
    if text.lower() in _ONLINE_WORDS or (online_only and not (text or city)):
        return Place(display="Online", continent=ONLINE)

    display = re.sub(r"\s*,\s*", ", ", text) or ", ".join(
        x for x in (city, country) if x
    )
    if display and state:
        display = _expand_state(display, state)
    if display and country and not _mentions_country(display, code):
        display = f"{display}, {country}"
    continent = ONLINE if online_only else (COUNTRIES[code][1] if code else "")
    return Place(display=display, country=country, continent=continent)


def item_continent(metadata: dict | None) -> str:
    return place_for(metadata).continent


# --------------------------------------------------------------------------- #
# Reading the place text
# --------------------------------------------------------------------------- #
def _clean(value) -> str:
    return " ".join(str(value or "").split()).strip(" .;,")


def _code(value) -> str:
    code = str(value or "").strip().upper()
    return code if code in COUNTRIES else ""


def _code_for_name(name: str) -> str:
    key = _clean(name).lower()
    return _BY_NAME.get(key, "") if key else ""


def _candidates(part: str) -> list[str]:
    """The ways one comma-separated part might name a place: itself, what is in
    its parentheses, what is outside them, and its pieces around a dash or a
    stray full stop ("Melbourne. Australia", "Mato Grosso do Sul - Brasil")."""
    out = [part]
    inner = re.findall(r"\(([^)]*)\)?", part)
    outer = re.sub(r"\([^)]*\)?", " ", part)
    out += [p for p in inner] + [outer]
    for piece in list(out):
        out += re.split(r"\s+[-–—]\s+|\.\s+", piece)
    return [c for c in (_clean(x).strip("() ") for x in out) if c]


def _read_tail(text: str) -> tuple[str, str]:
    """``(country code, US state code)`` read from the end of ``text``; empty
    strings when nothing there names a country."""
    parts = [p for p in (_clean(x) for x in text.split(",")) if p]
    zip_state = _ZIP_STATE.search(text)
    if zip_state and zip_state.group(1) in _US_STATES:
        return "US", zip_state.group(1)
    for index in range(len(parts) - 1, -1, -1):
        if index < len(parts) - 2:
            break  # only the last two parts name a region or a country
        last = index == len(parts) - 1
        for cand in _candidates(parts[index]):
            key = cand.lower()
            if last and len(parts) > 1 and cand in _US_STATES:
                return "US", cand
            if key in _BY_NAME:
                return _BY_NAME[key], ""
            if len(cand) == 2 and cand.isupper() and cand in COUNTRIES and last:
                return cand, ""
            if key in _STATE_NAMES:
                return "US", ""
            if key in _CA_PROVINCES:
                return "CA", ""
    return "", ""


def _expand_state(display: str, state: str) -> str:
    """``"Ann Arbor, MI"`` → ``"Ann Arbor, Michigan"``; a ZIP-coded address is
    left as written."""
    parts = [p.strip() for p in display.split(",")]
    if parts and parts[-1] == state:
        parts[-1] = _US_STATES[state]
    return ", ".join(parts)


def _mentions_country(display: str, code: str) -> bool:
    low = display.lower()
    names = [COUNTRIES[code][0].lower()] + [
        alias for alias, c in _ALIASES.items() if c == code
    ]
    return any(re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", low) for n in names)

"""Parse ship-to address strings into Sage 100 address components.

Ship-to strings come in varied human-written formats. This parser is
best-effort — it handles known patterns from the sample data but will
produce warnings for addresses it can't fully parse. Every order goes
on Hold for review, so imperfect parsing is acceptable.
"""

import re

# US zip: 5 digits or 5+4. Canadian postal: A1A 1A1 or A1A1A1.
ZIP_US = re.compile(r"\b(\d{5}(?:-\d{4})?)\b")
ZIP_CA = re.compile(r"\b([A-Z]\d[A-Z]\s?\d[A-Z]\d)\b", re.IGNORECASE)

# US state abbreviations
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

# Full state names -> abbreviations (common ones from sample data)
STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
    "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI",
    "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
    "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME",
    "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO",
    "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
    "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY",
    # Canadian provinces
    "QUEBEC": "QC", "ONTARIO": "ON", "BRITISH COLUMBIA": "BC",
    "ALBERTA": "AB", "MANITOBA": "MB", "SASKATCHEWAN": "SK",
    "NOVA SCOTIA": "NS", "NEW BRUNSWICK": "NB",
    "PRINCE EDWARD ISLAND": "PE", "NEWFOUNDLAND": "NL",
}

# Prefixes to strip from ship-to before parsing
VETERAN_PREFIX = re.compile(
    r"^VETERAN\s*[-–—]\s*(ship to veteran'?s? address:\s*)?",
    re.IGNORECASE,
)


def parse_ship_to(raw_str):
    """Parse a ship-to string into Sage address components.

    Returns a dict with keys: ShipToName, ShipToAddress1, ShipToAddress2,
    ShipToAddress3, ShipToCity, ShipToState, ShipToZipCode, ShipToCountryCode.
    Missing components are empty strings.
    """
    result = {
        "ShipToName": "",
        "ShipToAddress1": "",
        "ShipToAddress2": "",
        "ShipToAddress3": "",
        "ShipToCity": "",
        "ShipToState": "",
        "ShipToZipCode": "",
        "ShipToCountryCode": "",
    }

    if not raw_str or not raw_str.strip():
        return result

    text = raw_str.strip()

    # Strip veteran prefix
    text = VETERAN_PREFIX.sub("", text).strip()

    # Detect Canadian address
    is_canadian = _is_canadian_address(text)
    if is_canadian:
        result["ShipToCountryCode"] = "CAN"

    # Extract zip code
    zip_code, text = _extract_zip(text, is_canadian)
    result["ShipToZipCode"] = zip_code

    # Remove trailing "Canada" if present
    text = re.sub(r",?\s*Canada\s*$", "", text, flags=re.IGNORECASE).strip()

    # Split into parts by comma
    parts = [p.strip() for p in text.split(",") if p.strip()]

    if not parts:
        return result

    # Extract state from the last part (or second-to-last)
    state, parts = _extract_state(parts)
    result["ShipToState"] = state

    # The last remaining part is typically the city
    if parts:
        city_candidate = parts.pop().strip()
        result["ShipToCity"] = city_candidate

    # First part is typically the name (person, facility, business)
    # Remaining parts are address lines
    if parts:
        # Check if first part looks like a name (no street indicators)
        first = parts[0]
        if _looks_like_name(first) and len(parts) > 1:
            result["ShipToName"] = first
            address_parts = parts[1:]
        else:
            # Everything is address — no separate name
            address_parts = parts

        # Fill Address1, Address2, Address3 (max 3 lines, max 40 chars each)
        for i, addr in enumerate(address_parts[:3]):
            result[f"ShipToAddress{i + 1}"] = addr[:40]

    return result


def _is_canadian_address(text):
    """Check if an address looks Canadian."""
    if ZIP_CA.search(text):
        return True
    if re.search(r"\bCanada\b", text, re.IGNORECASE):
        return True
    if re.search(r"\bQuebec\b|\bOntario\b|\bAlberta\b|\bBritish Columbia\b",
                 text, re.IGNORECASE):
        return True
    return False


def _extract_zip(text, is_canadian):
    """Find and remove zip code from text. Returns (zip_code, remaining_text).

    Uses the LAST match to avoid grabbing street numbers like '15956'.
    """
    if is_canadian:
        matches = list(ZIP_CA.finditer(text))
        if matches:
            match = matches[-1]  # last match
            zip_code = match.group(1).upper()
            # Normalize to "A1A 1A1" format
            zip_code = zip_code.replace(" ", "")
            zip_code = zip_code[:3] + " " + zip_code[3:]
            text = text[:match.start()] + text[match.end():]
            return zip_code, text.strip().rstrip(",").strip()

    matches = list(ZIP_US.finditer(text))
    if matches:
        match = matches[-1]  # last match — zip is typically at the end
        zip_code = match.group(1)
        text = text[:match.start()] + text[match.end():]
        return zip_code, text.strip().rstrip(",").strip()

    return "", text


def _extract_state(parts):
    """Find and remove state from parts list. Returns (state_abbrev, remaining_parts)."""
    if not parts:
        return "", parts

    # Check if the last part contains a state
    last = parts[-1].strip()

    # Try splitting last part on space — state might be embedded with city
    # e.g. "BROOKLYN NY" or "Seattle WA"
    tokens = last.split()

    # Check last token for state abbreviation
    if tokens and tokens[-1].upper() in US_STATES:
        state = tokens[-1].upper()
        remainder = " ".join(tokens[:-1]).strip()
        if remainder:
            parts[-1] = remainder
        else:
            parts.pop()
        return state, parts

    # Check for full state names
    upper_last = last.upper().strip()
    if upper_last in STATE_NAMES:
        parts.pop()
        return STATE_NAMES[upper_last], parts

    # Check for two-word state names spanning the last part
    for state_name, abbrev in STATE_NAMES.items():
        if upper_last.endswith(state_name):
            remainder = last[:len(last) - len(state_name)].strip().rstrip(",").strip()
            if remainder:
                parts[-1] = remainder
            else:
                parts.pop()
            return abbrev, parts

    return "", parts


def _looks_like_name(text):
    """Heuristic: does this text look like a person/org name rather than a street address?"""
    street_indicators = re.compile(
        r"\b(\d+\s|ST\b|AVE\b|AVENUE\b|BLVD\b|DRIVE\b|DR\b|RD\b|ROAD\b|"
        r"STREET\b|LANE\b|LN\b|WAY\b|COURT\b|CT\b|PLACE\b|PL\b|"
        r"SUITE\b|STE\b|FLOOR\b|#)",
        re.IGNORECASE,
    )
    return not street_indicators.search(text)

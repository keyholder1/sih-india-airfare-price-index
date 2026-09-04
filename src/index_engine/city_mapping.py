"""Controlled IATA-code <-> DGCA-city-name mapping.

Deliberately NOT fuzzy matching: airfare observations use IATA codes
(BLR, DEL, ...) and the DGCA traffic file uses full city names as
published (DELHI, BENGALURU, ...). Every mapping below is verified by
hand against the actual distinct city-name strings in
data/traffic/dgca_domestic_city_pairs.csv (checked 2026-08-31) — see the
comment on each entry.

Deliberately excluded rather than merged:
    "MUMBAI (MUMBAI)"       - a separate, much smaller entry (336 rows)
                              alongside the dominant "MUMBAI" (7,351 rows);
                              merging them would silently double-count.
    "MUMBAI (NAVI MUMBAI)"  - a genuinely different airport (Navi Mumbai
                              International), not Mumbai/BOM.

Add new entries here (and verify the exact string against the CSV) rather
than guessing — an unmapped city silently drops that route's DGCA weight
to "unavailable," which is the safe failure mode, not a wrong number.
"""

from __future__ import annotations

from typing import Dict

IATA_TO_CITY: Dict[str, str] = {
    "DEL": "DELHI",
    "BOM": "MUMBAI",
    "BLR": "BENGALURU",
    "HYD": "HYDERABAD",
    "MAA": "CHENNAI",
    "CCU": "KOLKATA",
    # Added when expanding route coverage beyond the original 6 metros
    # (see docs/methodology.md "Route Coverage Expansion"). Each verified
    # against the real city-name string in data/traffic/dgca_domestic_city_pairs.csv
    # AND against the standard, unambiguous public IATA code for that airport.
    "PNQ": "PUNE",
    "AMD": "AHMEDABAD",
    "SXR": "SRINAGAR",
    "GAU": "GUWAHATI",
    "PAT": "PATNA",
    "COK": "KOCHI",
    "LKO": "LUCKNOW",
    "IXC": "CHANDIGARH",
    "VNS": "VARANASI",
    "IXR": "RANCHI",
    "IDR": "INDORE",
    "RPR": "RAIPUR",
    "BBI": "BHUBANESWAR",
    "CJB": "COIMBATORE",
    "ATQ": "AMRITSAR",
    "IXA": "AGARTALA",
    "IXB": "BAGDOGRA",
    "IXL": "LEH",
    "GOI": "DABOLIM",  # DGCA lists Goa's airport by its old name "DABOLIM"
    "TRV": "TRIVANDRUM",  # DGCA lists Thiruvananthapuram by its old name "TRIVANDRUM"
}

CITY_TO_IATA: Dict[str, str] = {city: iata for iata, city in IATA_TO_CITY.items()}


def iata_to_city(code: str) -> str:
    code = code.upper()
    if code not in IATA_TO_CITY:
        raise KeyError(
            f"No verified DGCA city-name mapping for IATA code {code!r}. "
            "Add and verify it in index_engine.city_mapping.IATA_TO_CITY before using it."
        )
    return IATA_TO_CITY[code]


def city_to_iata(city: str) -> str:
    city = city.upper()
    if city not in CITY_TO_IATA:
        raise KeyError(
            f"No verified IATA mapping for DGCA city name {city!r}. "
            "Add and verify it in index_engine.city_mapping.IATA_TO_CITY before using it."
        )
    return CITY_TO_IATA[city]

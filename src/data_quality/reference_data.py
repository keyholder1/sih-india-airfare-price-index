"""Small, hand-maintained reference lists used for FLAGGING (never rejecting).

Deliberately not fuzzy-matched and not exhaustive, in the same spirit as
``index_engine.city_mapping``: an unrecognized value here means "we don't
recognize it yet", not "it's wrong". A record with an airline or airport
missing from these lists is still eligible to be VALID or FLAGGED — it is
never REJECTED for that reason alone (see docs/data_quality.md).
"""

from __future__ import annotations

from typing import FrozenSet

from index_engine.city_mapping import IATA_TO_CITY

#: Airports we have a verified DGCA-city mapping for. Anything else that is
#: still a well-formed 3-letter code is UNMAPPED_LOCATION (flag), not
#: INVALID_AIRPORT_CODE (reject) — see field_validation for the distinction.
KNOWN_AIRPORTS: FrozenSet[str] = frozenset(IATA_TO_CITY.keys())

#: Indian carriers operating (or recently operating) domestic service, used
#: only to flag UNKNOWN_AIRLINE. Matched case-insensitively after stripping
#: whitespace. Not authoritative — add to this set rather than rejecting a
#: legitimate new/rebranded carrier.
KNOWN_AIRLINES: FrozenSet[str] = frozenset(
    name.upper()
    for name in (
        "IndiGo",
        "Air India",
        "AirIndia",
        "Air India Express",
        "AirIndiaExpress",
        "SpiceJet",
        "Vistara",
        "Akasa",
        "Akasa Air",
        "AllianceAir",
        "Alliance Air",
        "Go First",
        "GoFirst",
        "GoAir",
        "Star Air",
        "StarAir",
        "FlyBig",
        "TruJet",
        "IndiaOne Air",
    )
)

#: Currencies this INR-only prototype index accepts. Anything else is
#: NON_INR_CURRENCY (rejected) rather than silently treated as INR — see
#: docs/data_contract.md "What happens when currency isn't INR": no FX
#: conversion methodology exists in this project yet.
ALLOWED_CURRENCIES: FrozenSet[str] = frozenset({"INR"})

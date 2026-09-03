"""IndiGo source adapter — scaffold, not a working live integration.

IndiGo operates a developer/NDC API program (see
``docs/scraper.md`` "Source evaluation" for the full write-up). This
module exists so that:

1. The credential/environment-variable plumbing is ready ahead of time.
2. A teammate who obtains real, approved IndiGo API access has exactly
   one place to add the actual request/parsing logic
   (:meth:`IndiGoSource._call_api`) without touching anything else in
   this package — ``scraper.runner`` only ever talks to the
   :class:`~scraper.source.FareSource` interface.

**This adapter does NOT call any real IndiGo endpoint today.** No
endpoint path, request schema, response schema, or auth flow is invented
here — the brief this project follows explicitly forbids fabricating API
contracts. Until someone obtains verified IndiGo API documentation and
approved credentials, :meth:`search_fares` always returns a structured
``SOURCE_UNAVAILABLE`` result, distinguishing two honest cases:

- No credentials configured at all (the common case today).
- Credentials configured, but the real request/response contract still
  needs to be filled in at :meth:`_call_api` (a `NotImplementedError`
  guard, not a silent fake success).

See docs/scraper.md "Adding a real source later" for the exact steps to
complete this adapter once real API access exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .models import SourceCallResult
from .source import FareSource, SearchRequest

#: Environment variables this adapter reads. Never hard-code real values
#: here or anywhere else in this repo -- see docs/scraper.md "Credential
#: handling".
ENV_API_KEY = "INDIGO_API_KEY"
ENV_USERNAME = "INDIGO_USERNAME"
ENV_PASSWORD = "INDIGO_PASSWORD"
ENV_BASE_URL = "INDIGO_API_BASE_URL"  # optional override, e.g. a sandbox host


@dataclass(frozen=True)
class IndiGoCredentials:
    api_key: str
    username: Optional[str] = None
    password: Optional[str] = None
    base_url: Optional[str] = None


def load_credentials_from_env() -> Optional[IndiGoCredentials]:
    """Read IndiGo credentials from environment variables.

    Returns ``None`` if the minimum required variable (``INDIGO_API_KEY``)
    is absent -- callers must treat that as "source unavailable," never as
    "use a placeholder." Nothing here ever logs or returns the credential
    values themselves, so accidental leakage into a log line or JSON
    output is not possible via this function.
    """
    api_key = os.environ.get(ENV_API_KEY)
    if not api_key:
        return None
    return IndiGoCredentials(
        api_key=api_key,
        username=os.environ.get(ENV_USERNAME),
        password=os.environ.get(ENV_PASSWORD),
        base_url=os.environ.get(ENV_BASE_URL),
    )


class IndiGoSource(FareSource):
    """Scaffold adapter for IndiGo's developer/NDC API.

    Construct with no arguments to read credentials from the environment
    (the normal path); pass ``credentials`` explicitly only for tests.
    """

    name = "IndiGo"

    def __init__(self, credentials: Optional[IndiGoCredentials] = None) -> None:
        self._credentials = credentials if credentials is not None else load_credentials_from_env()

    def search_fares(self, request: SearchRequest) -> SourceCallResult:
        if self._credentials is None:
            return SourceCallResult(
                status="SOURCE_UNAVAILABLE",
                observations=[],
                error_detail=(
                    f"IndiGo API credentials not configured (set {ENV_API_KEY}; "
                    f"optionally {ENV_USERNAME}, {ENV_PASSWORD}, {ENV_BASE_URL}). "
                    "See docs/scraper.md 'Source evaluation' -- IndiGo has a real "
                    "developer/NDC API program, but production approval and a "
                    "verified request/response contract are required before this "
                    "adapter can make a real call."
                ),
            )

        try:
            return self._call_api(request)
        except NotImplementedError as exc:
            # Credentials exist, but the real request/parsing logic has not
            # been implemented against a verified IndiGo API contract yet.
            # This is deliberately NOT a fabricated success -- see module
            # docstring.
            return SourceCallResult(
                status="SOURCE_UNAVAILABLE",
                observations=[],
                error_detail=str(exc),
            )

    def _call_api(self, request: SearchRequest) -> SourceCallResult:
        """Real IndiGo API call -- intentionally not implemented.

        Fill this in only once a verified IndiGo API contract (endpoint
        URL, auth flow, request schema, response schema) has actually been
        obtained -- e.g. from an approved developer/NDC account. When that
        happens:

        1. Build the authenticated request using ``self._credentials``.
        2. Call the real endpoint with the shared retry/rate-limit
           machinery already used everywhere else in this package
           (``scraper.rate_limit`` -- ``scraper.runner`` applies this at
           the orchestration layer, so this method itself should stay a
           single plain HTTP call).
        3. Map each real fare in the response to a
           ``scraper.models.RawFareObservation`` -- required fields
           (``observation_id, airline, origin, destination, flight_date,
           booking_date, total_fare, currency``) must come from real
           response fields, never invented or defaulted to a guess.
        4. Return ``SourceCallResult(status="SUCCESS", observations=[...])``
           on success, or the appropriate status
           (``EMPTY_RESULT``/``HTTP_ERROR``/``PARSE_ERROR``/
           ``MALFORMED_RESPONSE``) otherwise -- never raise for an
           ordinary "no fares"/"bad response" outcome (see
           ``FareSource.search_fares`` docstring).

        Until then, this stays a `NotImplementedError` so the failure is
        loud and explicit rather than silently returning fake data.
        """
        raise NotImplementedError(
            "IndiGo credentials are configured, but no verified IndiGo API "
            "request/response contract has been implemented yet. See "
            "IndiGoSource._call_api docstring for what's needed to complete "
            "this adapter -- do not fabricate the endpoint or response shape."
        )

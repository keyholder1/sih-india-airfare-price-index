import json

import pytest

from scraper.routes import RouteSpec, load_routes, route_pairs


def test_load_routes_reads_from_the_real_route_file_not_hardcoded():
    routes = load_routes()
    # 100 rows in the file, 12 of which have a deliberately null
    # origin_iata/destination_iata (see city_mapping.py's documented
    # "MUMBAI (MUMBAI)"/"MUMBAI (NAVI MUMBAI)" exclusions) and are
    # therefore not IATA-mappable routes a source could ever be asked
    # about -- load_routes() skips those, leaving 88.
    assert len(routes) == 88  # matches data/routes/recommended_routes.json today
    assert all(isinstance(r, RouteSpec) for r in routes)


def test_tier_1_filter_returns_only_tier_1_routes():
    routes = load_routes(tiers=(1,))
    assert len(routes) == 18  # 20 tier-1 rows, 2 of them null-IATA (excluded)
    assert all(r.tier == 1 for r in routes)


def test_tier_1_and_2_filter_combines_tiers():
    routes = load_routes(tiers=(1, 2))
    assert len(routes) == 46  # 50 tier-1/2 rows, 4 null-IATA (excluded)
    assert all(r.tier in (1, 2) for r in routes)


def test_no_tier_filter_returns_everything():
    all_routes = load_routes(tiers=None)
    assert len(all_routes) == 88


def test_routes_with_no_iata_mapping_are_never_returned():
    # These rows exist in the file (with currently_covered=False) but have
    # no origin_iata/destination_iata -- a source can never be sensibly
    # asked about them, so load_routes() must never hand one out,
    # regardless of which tier(s) are requested.
    routes = load_routes(tiers=None)
    assert all(r.origin is not None and r.destination is not None for r in routes)
    assert not any(r.route == "None-None" for r in routes)


def test_route_property_and_pairs_helper():
    routes = load_routes(tiers=(1,))[:2]
    assert routes[0].route == f"{routes[0].origin}-{routes[0].destination}"
    pairs = route_pairs(routes)
    assert pairs == [(r.origin, r.destination) for r in routes]


def test_route_loading_is_not_hardcoded_it_reflects_the_actual_file(tmp_path):
    """Prove the route count comes from the file, not a constant baked into
    the scraper — point at a small fixture file with a different shape."""
    fixture = {
        "source": "test-fixture",
        "weight_period": "n/a",
        "tier_cutoffs": {"tier_1_end_rank": 1, "tier_2_end_rank": 2, "tier_3_end_rank": 2},
        "routes": [
            {
                "origin_city": "A", "destination_city": "B", "origin_iata": "AAA", "destination_iata": "BBB",
                "priority": 1, "tier": 1, "national_weight": 0.5, "currently_covered": True,
            },
            {
                "origin_city": "C", "destination_city": "D", "origin_iata": "CCC", "destination_iata": "DDD",
                "priority": 2, "tier": 2, "national_weight": 0.5, "currently_covered": False,
            },
        ],
    }
    path = tmp_path / "fixture_routes.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    routes = load_routes(path=str(path))
    assert len(routes) == 2
    assert routes[0].origin == "AAA"

    tier1_only = load_routes(path=str(path), tiers=(1,))
    assert len(tier1_only) == 1
    assert tier1_only[0].destination == "BBB"

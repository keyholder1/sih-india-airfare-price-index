from pathlib import Path

import pandas as pd

from index_engine.route_selection import (
    assign_tiers,
    bidirectional_summary,
    city_level_traffic,
    coverage_at_n,
    coverage_scenarios,
    find_routes_for_target_coverage,
    mark_currently_covered,
    rank_routes_by_traffic,
    target_coverage_table,
    underrepresented_cities,
)
from index_engine.traffic import aggregate_period, latest_available_period, load_dgca_traffic, national_weights, rolling_window, to_directional, validate_traffic

REAL_DGCA_CSV = Path(__file__).parent.parent / "data" / "traffic" / "dgca_domestic_city_pairs.csv"


def _sample_national_weights():
    return pd.DataFrame(
        {
            "origin": ["A", "B", "C", "D"],
            "destination": ["A2", "B2", "C2", "D2"],
            "passengers": [500, 300, 150, 50],
            "national_weight": [0.5, 0.3, 0.15, 0.05],
        }
    )


def test_rank_routes_by_traffic_orders_descending_with_cumulative():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    assert list(ranked["origin"]) == ["A", "B", "C", "D"]
    assert ranked["rank"].tolist() == [1, 2, 3, 4]
    assert abs(ranked["cumulative_coverage"].iloc[-1] - 1.0) < 1e-9


def test_coverage_at_n():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    assert abs(coverage_at_n(ranked, 2) - 0.8) < 1e-9
    assert coverage_at_n(ranked, 0) == 0.0


def test_find_routes_for_target_coverage():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    assert find_routes_for_target_coverage(ranked, 0.5) == 1
    assert find_routes_for_target_coverage(ranked, 0.8) == 2
    assert find_routes_for_target_coverage(ranked, 0.95) == 3
    assert find_routes_for_target_coverage(ranked, 0.0) == 0


def test_coverage_scenarios_reports_incremental_gain():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    scenarios = coverage_scenarios(ranked, [1, 2, 4])
    assert abs(scenarios.loc[scenarios.routes == 2, "incremental_gain"].iloc[0] - 0.3) < 1e-9


def test_target_coverage_table():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    table = target_coverage_table(ranked, [0.5, 0.8])
    assert table.loc[table.target_coverage == 0.5, "minimum_routes"].iloc[0] == 1


def test_directional_routes_are_not_merged_in_ranking():
    df = pd.DataFrame(
        {"origin": ["BLR", "DEL"], "destination": ["DEL", "BLR"], "passengers": [100, 90], "national_weight": [0.55, 0.45]}
    )
    ranked = rank_routes_by_traffic(df)
    assert len(ranked) == 2  # BLR->DEL and DEL->BLR remain separate rows


def test_bidirectional_summary_combines_for_prioritization_only():
    df = pd.DataFrame(
        {"origin": ["BLR", "DEL"], "destination": ["DEL", "BLR"], "passengers": [100, 90], "national_weight": [0.55, 0.45]}
    )
    ranked = rank_routes_by_traffic(df)
    summary = bidirectional_summary(ranked)
    assert len(summary) == 1
    assert summary["passengers"].iloc[0] == 190
    # original directional frame must be untouched
    assert len(ranked) == 2


def test_assign_tiers_uses_rank_cutoffs():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    tiered = assign_tiers(ranked, tier_cutoffs=(1, 2, 3))
    assert tiered.loc[tiered["rank"] == 1, "tier"].iloc[0] == 1
    assert tiered.loc[tiered["rank"] == 2, "tier"].iloc[0] == 2
    assert tiered.loc[tiered["rank"] == 3, "tier"].iloc[0] == 3
    assert tiered.loc[tiered["rank"] == 4, "tier"].iloc[0] == 4


def test_mark_currently_covered():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    marked = mark_currently_covered(ranked, [("A", "A2")])
    assert bool(marked.loc[marked.origin == "A", "currently_covered"].iloc[0]) is True
    assert bool(marked.loc[marked.origin == "B", "currently_covered"].iloc[0]) is False


def test_zero_passenger_route_ranks_last_not_excluded():
    df = pd.DataFrame(
        {"origin": ["A", "B"], "destination": ["A2", "B2"], "passengers": [100, 0], "national_weight": [1.0, 0.0]}
    )
    ranked = rank_routes_by_traffic(df)
    assert ranked.iloc[-1]["origin"] == "B"
    assert ranked.iloc[-1]["national_weight"] == 0.0


def test_missing_route_has_no_row_rather_than_a_fabricated_zero():
    ranked = rank_routes_by_traffic(_sample_national_weights())
    assert "Z" not in ranked["origin"].values  # a route absent from the DGCA window simply isn't in the table


def test_city_level_traffic_and_underrepresented_cities():
    df = pd.DataFrame(
        {
            "origin": ["A", "A", "A", "B"],
            "destination": ["X1", "X2", "X3", "Y1"],
            "passengers": [40, 40, 40, 100],
        }
    )
    city_traffic = city_level_traffic(df)
    # City A has 120 total spread across 3 small routes; city B has 100 on one big route.
    assert city_traffic.loc[city_traffic.city == "A", "passengers"].iloc[0] == 120
    top_route_cities = {"B", "Y1"}  # only the single biggest route made a hypothetical top-1 cut
    gaps = underrepresented_cities(city_traffic, top_route_cities, top_n_cities=2)
    assert "A" in gaps["city"].values  # high total traffic, but none of its routes cracked the top-N route list


def test_actual_current_coverage_differs_from_best_possible_top_n_coverage():
    """Regression test for a real documentation ambiguity found in audit:
    'our actual 10 demo routes' coverage (8.8%) and 'the best possible 10
    routes by traffic' coverage (10.4%) are different numbers by
    definition, since our demo routes were chosen for metro-pair variety,
    not because they are literally the top-10-ranked routes nationwide.
    Both numbers are correct for what they measure; they must never be
    quoted interchangeably as if they were the same "10 routes" figure."""
    from index_engine.city_mapping import iata_to_city
    from index_engine.traffic import build_dgca_weights

    current_routes = [
        ("BLR", "DEL"), ("DEL", "BOM"), ("BOM", "BLR"), ("DEL", "HYD"),
        ("BLR", "HYD"), ("MAA", "DEL"), ("DEL", "MAA"), ("BOM", "DEL"),
        ("CCU", "DEL"), ("BLR", "BOM"),
    ]
    _, diagnostics = build_dgca_weights(str(REAL_DGCA_CSV), current_routes)
    actual_coverage = diagnostics["traffic_weight_coverage"]

    raw = load_dgca_traffic(str(REAL_DGCA_CSV))
    valid, _ = validate_traffic(raw)
    long_df = to_directional(valid, source="DGCA")
    end = latest_available_period(long_df)
    start, end = rolling_window(end, 12)
    agg = aggregate_period(long_df, start, end)
    ranked = rank_routes_by_traffic(national_weights(agg))
    best_possible_coverage = coverage_at_n(ranked, len(current_routes))

    assert abs(actual_coverage - 0.088) < 0.01
    assert abs(best_possible_coverage - 0.104) < 0.01
    assert best_possible_coverage > actual_coverage  # best-possible must never be less than what we actually cover

    # Confirm the reason: our current routes are NOT literally rank 1-10.
    current_city_routes = [(iata_to_city(o), iata_to_city(d)) for o, d in current_routes]
    marked = mark_currently_covered(ranked, current_city_routes)
    our_ranks = sorted(marked.loc[marked["currently_covered"], "rank"].tolist())
    assert our_ranks != list(range(1, 11))


def test_real_dgca_coverage_curve_matches_verified_figures():
    """Regression test against the real committed dataset: locks in the
    coverage-at-N figures computed and reported in docs/methodology.md."""
    raw = load_dgca_traffic(str(REAL_DGCA_CSV))
    valid, _ = validate_traffic(raw)
    long_df = to_directional(valid, source="DGCA")
    end = latest_available_period(long_df)
    start, end = rolling_window(end, 12)
    agg = aggregate_period(long_df, start, end)
    nat = national_weights(agg)
    ranked = rank_routes_by_traffic(nat)

    assert len(ranked) > 2000  # real network, not a toy fixture
    assert abs(coverage_at_n(ranked, 10) - 0.104) < 0.01
    assert abs(coverage_at_n(ranked, 100) - 0.445) < 0.01
    assert find_routes_for_target_coverage(ranked, 0.5) in range(120, 135)

"""
Analytics package for Fantrax API Wrapper.
"""

from .manager_efficiency import (
    compute_optimal_lineup_score,
    calculate_manager_efficiency,
    calculate_median_standings,
    calculate_optimal_standings,
    compare_standings_vs_optimal,
)
from .waiver_wire import evaluate_waiver_candidates
from .stat_normalizer import normalize_per_90_stats, compute_positional_opponent_averages

__all__ = [
    "compute_optimal_lineup_score",
    "calculate_manager_efficiency",
    "calculate_median_standings",
    "calculate_optimal_standings",
    "compare_standings_vs_optimal",
    "evaluate_waiver_candidates",
    "normalize_per_90_stats",
    "compute_positional_opponent_averages",
]

"""
Example usage script demonstrating the Fantrax API Wrapper.
"""

import os
import sys

# Ensure soccer package directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fantrax_wrapper import (
    FantraxClient,
    FantasyScoringEngine,
    calculate_manager_efficiency,
    calculate_median_standings,
    evaluate_waiver_candidates,
)


def main():
    league_id = "de19pr8smd5cytbm"
    cookie_path = "fantraxloggedin.cookie"

    print("=== Fantrax API Wrapper Demonstration ===")
    print(f"Initializing FantraxClient for League ID: {league_id}")

    client = FantraxClient(league_id=league_id, cookie_path=cookie_path)

    # 1. Scoring Engine Demo
    print("\n--- 1. Position-Specific Fantasy Scoring Engine ---")
    scoring = FantasyScoringEngine()
    midfielder_stats = {"G": 1, "KP": 3, "SOT": 2, "TKW": 2, "DIS": -1}
    mid_score = scoring.calculate_fantasy_score(midfielder_stats, "M")
    mid_afpts = scoring.calculate_adjusted_fantasy_score(midfielder_stats, "M")
    print(f"Sample Midfielder Box Score: {midfielder_stats}")
    print(f"Calculated FPts: {mid_score} | Adjusted FPts (aFPts): {mid_afpts}")

    # 2. Matchup Schedule & Standings Demo
    print("\n--- 2. Fetching Matchup Schedule & League Table ---")
    try:
        matchups_df = client.get_matchups(through_week=5, as_dataframe=True)
        print(f"Fetched {len(matchups_df)} matchup rows across weeks 1-5.")
        if not matchups_df.empty:
            print(matchups_df.head(4)[["week", "team", "score", "opponent", "opponent_score", "result"]])
    except Exception as e:
        print(f"API Request Notice: {e}")

    # 3. Manager Efficiency Analytics Demo
    print("\n--- 3. Analytics: Manager Efficiency & Standings Against Median ---")
    mock_matchups = matchups_df if 'matchups_df' in locals() and not matchups_df.empty else None
    if mock_matchups is not None and "score" in mock_matchups.columns:
        mock_matchups["max_points_for"] = mock_matchups["score"] + 12.5  # Simulated max points
        efficiency_summary = calculate_manager_efficiency(mock_matchups)
        print("Manager Efficiency Summary:")
        print(efficiency_summary)

        median_standings = calculate_median_standings(mock_matchups)
        print("\nStandings Against Weekly Median Score:")
        print(median_standings)

    print("\n=== Demonstration Completed Successfully ===")


if __name__ == "__main__":
    main()

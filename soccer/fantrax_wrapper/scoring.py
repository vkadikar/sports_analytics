"""
Fantasy Premier League scoring rules engine and FPts calculator.
"""

from typing import Dict, Optional, Union
import pandas as pd


# Default Fantrax Fantasy Premier League Scoring Weights per Position
DEFAULT_SCORING_RULES_GOALKEEPER = {
    "AER": 1.0,     # Aerials Won
    "AT": 7.0,      # Assists (Total)
    "CS": 8.0,      # Clean Sheets On Field
    "DIS": -0.5,    # Dispossessed
    "GAO": -2.0,    # Goals Against
    "G": 10.0,      # Goals
    "HCS": 1.0,     # High Claims Succeeded
    "INT": 1.0,     # Interceptions
    "OG": -5.0,     # Own Goals
    "PKS": 8.0,     # Penalty Kick Saves
    "RC": -7.0,     # Red Cards
    "SOT": 2.0,     # Shots on Target
    "SM": 1.0,      # Smothers
    "COS": 1.0,     # Successful Dribbles (Contests Succeeded)
    "CLR": 0.25,    # Effective Clearances
    "KP": 2.0,      # Key Passes (Assists on Shots)
    "SV": 2.0,      # Saves
    "TKW": 1.0,     # Tackles Won
    "YC": -2.0,     # Yellow Cards
}

DEFAULT_SCORING_RULES_DEFENDER = {
    "ACNC": 1.0,    # Accurate Crosses (No Corners)
    "AER": 1.0,     # Aerials Won
    "AT": 7.0,      # Assists (Total)
    "BS": 1.0,      # Blocked Shots
    "CS": 6.0,      # Clean Sheets On Field
    "DIS": -0.5,    # Dispossessed
    "GAO": -2.0,    # Goals Against Outfielders
    "G": 10.0,      # Goals
    "INT": 1.0,     # Interceptions
    "OG": -5.0,     # Own Goals
    "PKD": 2.0,     # Penalty Kicks Drawn
    "PKM": -4.0,    # Penalty Kicks Missed
    "RC": -7.0,     # Red Cards
    "SOT": 2.0,     # Shots on Target
    "COS": 1.0,     # Successful Dribbles (Contests Succeeded)
    "CLR": 0.25,    # Effective Clearances
    "KP": 2.0,      # Key Passes (Assists on Shots)
    "TKW": 1.0,     # Tackles Won
    "YC": -2.0,     # Yellow Cards
}

DEFAULT_SCORING_RULES_MIDFIELDER = {
    "ACNC": 1.0,    # Accurate Crosses (No Corners)
    "AER": 0.5,     # Aerials Won
    "AT": 6.0,      # Assists (Total)
    "BS": 1.0,      # Blocked Shots
    "CS": 1.0,      # Clean Sheets On Field
    "DIS": -0.5,    # Dispossessed
    "G": 9.0,       # Goals
    "INT": 1.0,     # Interceptions
    "OG": -5.0,     # Own Goals
    "PKD": 2.0,     # Penalty Kicks Drawn
    "PKM": -4.0,    # Penalty Kicks Missed
    "RC": -7.0,     # Red Cards
    "SOT": 2.0,     # Shots on Target
    "COS": 1.0,     # Successful Dribbles (Contests Succeeded)
    "KP": 2.0,      # Key Passes (Assists on Shots)
    "TKW": 1.0,     # Tackles Won
    "YC": -2.0,     # Yellow Cards
}

DEFAULT_SCORING_RULES_FORWARD = {
    "ACNC": 1.0,    # Accurate Crosses (No Corners)
    "AER": 0.5,     # Aerials Won
    "AT": 6.0,      # Assists (Total)
    "BS": 1.0,      # Blocked Shots
    "DIS": -0.5,    # Dispossessed
    "G": 9.0,       # Goals
    "INT": 1.0,     # Interceptions
    "OG": -5.0,     # Own Goals
    "PKD": 2.0,     # Penalty Kicks Drawn
    "PKM": -4.0,    # Penalty Kicks Missed
    "RC": -7.0,     # Red Cards
    "SOT": 2.0,     # Shots on Target
    "COS": 1.0,     # Successful Dribbles (Contests Succeeded)
    "KP": 2.0,      # Key Passes (Assists on Shots)
    "TKW": 1.0,     # Tackles Won
    "YC": -2.0,     # Yellow Cards
}


class FantasyScoringEngine:
    """Engine for calculating raw FPts and adjusted fantasy points (aFPts) from box score stats."""

    def __init__(self, custom_rules: Optional[Dict[str, Dict[str, float]]] = None):
        """Initialize FantasyScoringEngine.

        Args:
            custom_rules: Optional custom position -> stat -> multiplier dictionary mapping.
        """
        self.rules = {
            "G": DEFAULT_SCORING_RULES_GOALKEEPER.copy(),
            "D": DEFAULT_SCORING_RULES_DEFENDER.copy(),
            "M": DEFAULT_SCORING_RULES_MIDFIELDER.copy(),
            "F": DEFAULT_SCORING_RULES_FORWARD.copy(),
        }

        if custom_rules:
            for pos, rules in custom_rules.items():
                if pos in self.rules:
                    self.rules[pos].update(rules)

    def calculate_fantasy_score(
        self, stats: Dict[str, Union[int, float, str]], position: str
    ) -> float:
        """Calculates total Fantasy Points (FPts) for a given player stat dictionary and position.

        Args:
            stats: Dictionary mapping stat shortNames (case-insensitive) to numeric values.
            position: Player position string ('G', 'D', 'M', or 'F').

        Returns:
            Calculated fantasy points total (rounded to 2 decimal places).
        """
        pos = position.upper() if position else "M"
        pos_rules = self.rules.get(pos, self.rules["M"])

        # Normalize stat dict keys to upper case
        stats_normalized = {str(k).upper(): float(v) for k, v in stats.items() if str(v).replace('.', '', 1).replace('-', '', 1).isdigit()}

        score = 0.0
        for stat, weight in pos_rules.items():
            if stat in stats_normalized:
                score += weight * stats_normalized[stat]

        return round(score, 2)

    def calculate_adjusted_fantasy_score(
        self, stats: Dict[str, Union[int, float, str]], position: str
    ) -> float:
        """Calculates Adjusted Fantasy Points (aFPts) excluding Goals, Assists, and Defender Clean Sheets.

        Useful for measuring underlying non-luck performance.

        Args:
            stats: Dictionary mapping stat shortNames (case-insensitive) to numeric values.
            position: Player position string ('G', 'D', 'M', or 'F').

        Returns:
            Adjusted fantasy points total (rounded to 2 decimal places).
        """
        pos = position.upper() if position else "M"
        pos_rules = self.rules.get(pos, self.rules["M"])

        stats_normalized = {str(k).upper(): float(v) for k, v in stats.items() if str(v).replace('.', '', 1).replace('-', '', 1).isdigit()}

        score = 0.0
        for stat, weight in pos_rules.items():
            # Exclude G, AT/A, and Defender CS
            if stat in ["G", "AT", "A"] or (pos == "D" and stat == "CS"):
                continue
            if stat in stats_normalized:
                score += weight * stats_normalized[stat]

        return round(score, 2)

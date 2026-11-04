"""
Fantasy points model.

Fits one random forest per box score stat on all games before a gameweek, predicts each
player's stat line for that gameweek, then scores the line with the league's scoring rules.
"""

from typing import Dict

import pandas as pd
from fantrax_wrapper.scoring import FantasyScoringEngine
from sklearn.ensemble import RandomForestRegressor

from .features import CATEGORICAL_FEATURES, TARGET_STATS, feature_columns


def _encode_categoricals(features: pd.DataFrame) -> pd.DataFrame:
    """Replaces categorical features with integer codes."""
    encoded = features.copy()
    for col in CATEGORICAL_FEATURES:
        encoded[col] = pd.factorize(encoded[col])[0]
    return encoded


def train_stat_models(
    features: pd.DataFrame,
    week: int,
    n_estimators: int = 300,
    random_state: int = 42,
) -> Dict[str, RandomForestRegressor]:
    """Fits a random forest for each target stat on games before a gameweek.

    Args:
        features: Feature table from build_features.
        week: Gameweek being predicted. Only earlier matchweeks are used for training.
        n_estimators: Number of trees per forest.
        random_state: Seed for each forest.

    Returns:
        Dictionary mapping stat name to its fitted model.
    """
    encoded = _encode_categoricals(features)
    train = encoded[encoded["matchweek"] < week]
    if train.empty:
        raise ValueError(f"No games before matchweek {week} to train on")

    models = {}
    for stat in TARGET_STATS:
        model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state, n_jobs=-1)
        models[stat] = model.fit(train[feature_columns(stat)], train[stat])
    return models


def predict_gameweek(
    models: Dict[str, RandomForestRegressor],
    features: pd.DataFrame,
    week: int,
) -> pd.DataFrame:
    """Predicts each player's stat line and fantasy points for a gameweek.

    Args:
        models: Fitted models from train_stat_models, trained on the same feature table.
        features: Feature table from build_features.
        week: Gameweek to predict.

    Returns:
        DataFrame with one row per player, the predicted stats, and fpts_pred.
    """
    encoded = _encode_categoricals(features)
    in_week = encoded["matchweek"] == week
    if not in_week.any():
        raise ValueError(f"No fixtures for matchweek {week} in features")

    id_cols = ["player_id", "team", "opp", "position", "is_away", "matchweek"]
    predictions = features.loc[in_week, id_cols].reset_index(drop=True)
    for stat, model in models.items():
        predicted = model.predict(encoded.loc[in_week, feature_columns(stat)])
        predictions[stat] = pd.Series(predicted).round(2)

    engine = FantasyScoringEngine()
    predictions["fpts_pred"] = [
        engine.calculate_fantasy_score(stat_line, position)
        for stat_line, position in zip(predictions[list(models)].to_dict("records"), predictions["position"])
    ]
    return predictions

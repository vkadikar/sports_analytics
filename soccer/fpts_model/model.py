"""
Fantasy points model.

Fits one random forest per box score stat on all games before a gameweek, predicts each
player's stat line for that gameweek, then scores the line with the league's scoring rules.
Saved models are plain JSON and predict exactly what the fitted forests do.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Union

import numpy as np
import pandas as pd
from fantrax_wrapper.scoring import FantasyScoringEngine
from sklearn.ensemble import RandomForestRegressor

from .features import CATEGORICAL_FEATURES, TARGET_STATS, feature_columns

N_ESTIMATORS = 300
RANDOM_STATE = 42


class JsonForest:
    """A saved random forest. Trees are parallel arrays of node fields, with leaves marked by feature -2."""

    def __init__(self, trees: List[Dict[str, list]]):
        self.trees = [{field: np.asarray(values) for field, values in tree.items()} for tree in trees]

    @classmethod
    def from_sklearn(cls, forest: RandomForestRegressor) -> "JsonForest":
        trees = []
        for estimator in forest.estimators_:
            tree = estimator.tree_
            trees.append({
                "left": tree.children_left.tolist(),
                "right": tree.children_right.tolist(),
                "feature": tree.feature.tolist(),
                "threshold": tree.threshold.tolist(),
                "value": tree.value[:, 0, 0].tolist(),
            })
        return cls(trees)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        # scikit-learn compares float32 inputs against double thresholds
        values = X.to_numpy(dtype=np.float32)
        rows = np.arange(len(values))
        total = np.zeros(len(values))
        for tree in self.trees:
            nodes = np.zeros(len(values), dtype=int)
            active = tree["feature"][nodes] >= 0
            while active.any():
                at = nodes[active]
                go_left = values[rows[active], tree["feature"][at]] <= tree["threshold"][at]
                nodes[active] = np.where(go_left, tree["left"][at], tree["right"][at])
                active = tree["feature"][nodes] >= 0
            total += tree["value"][nodes]
        return total / len(self.trees)

    def to_json(self) -> List[Dict[str, list]]:
        return [{field: values.tolist() for field, values in tree.items()} for tree in self.trees]


class FptsModel:
    """One forest per target stat, trained on all games before a single gameweek."""

    def __init__(self, week: int, forests: Dict[str, Any], encoders: Dict[str, List[str]]):
        self.week = week
        self.forests = forests
        self.encoders = encoders

    @classmethod
    def train(cls, features: pd.DataFrame, week: int, n_estimators: int = N_ESTIMATORS) -> "FptsModel":
        """Fits the model for a gameweek.

        Args:
            features: Feature table from build_features.
            week: Gameweek being predicted. Only games played before it are used for training.
            n_estimators: Number of trees per forest.

        Returns:
            The fitted model.
        """
        encoders = {col: pd.factorize(features[col])[1].tolist() for col in CATEGORICAL_FEATURES}
        model = cls(week, {}, encoders)
        encoded = model._encode(features)
        train = encoded[encoded["played"] & (encoded["matchweek"] < week)]
        if train.empty:
            raise ValueError(f"No games before matchweek {week} to train on")

        for stat in TARGET_STATS:
            forest = RandomForestRegressor(n_estimators=n_estimators, random_state=RANDOM_STATE, n_jobs=-1)
            forest.fit(train[feature_columns(stat)], train[stat])
            model.forests[stat] = JsonForest.from_sklearn(forest)
        return model

    def _encode(self, features: pd.DataFrame) -> pd.DataFrame:
        """Replaces categorical features with integer codes. Unknown categories get a code of their own."""
        encoded = features.copy()
        for col, categories in self.encoders.items():
            codes = {category: code for code, category in enumerate(categories)}
            encoded[col] = encoded[col].map(codes).fillna(len(categories)).astype(int)
        return encoded

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        """Predicts each player's stat line and fantasy points for the model's gameweek.

        Args:
            features: Feature table from build_features, including the gameweek's fixtures.

        Returns:
            DataFrame with one row per player, the predicted stats summed over their fixtures, and fpts_pred.
        """
        in_week = features["matchweek"] == self.week
        if not in_week.any():
            raise ValueError(f"No fixtures for matchweek {self.week} in features")

        encoded = self._encode(features[in_week])
        predictions = features.loc[in_week, ["player_id", "team", "position"]].reset_index(drop=True)
        predictions["fixtures"] = [
            f"@{opp}" if away else opp for opp, away in zip(features.loc[in_week, "opp"], features.loc[in_week, "is_away"])
        ]
        for stat, forest in self.forests.items():
            predictions[stat] = np.round(forest.predict(encoded[feature_columns(stat)]), 2)

        per_player = predictions.groupby(["player_id", "team", "position"], as_index=False).agg(
            {"fixtures": list, **{stat: "sum" for stat in self.forests}}
        )
        engine = FantasyScoringEngine()
        per_player["fpts_pred"] = [
            engine.calculate_fantasy_score(line, position)
            for line, position in zip(per_player[list(self.forests)].to_dict("records"), per_player["position"])
        ]
        return per_player

    def save(self, path: Union[str, Path], metadata: Dict[str, Any]) -> None:
        """Writes the model as JSON, with every tree of every forest."""
        document = {
            **metadata,
            "week": self.week,
            "encoders": self.encoders,
            "features": {stat: feature_columns(stat) for stat in self.forests},
            "forests": {stat: forest.to_json() for stat, forest in self.forests.items()},
        }
        Path(path).write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "FptsModel":
        """Reads a model written by save."""
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        forests = {stat: JsonForest(trees) for stat, trees in document["forests"].items()}
        return cls(document["week"], forests, document["encoders"])

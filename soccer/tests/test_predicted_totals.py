"""
Tests for the League Hub endpoint behind predicted team totals on match cards.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("flask")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "league_hub")))

import app as hub
from fantrax_wrapper import predictions as predictions_module


class TestPredictedTotals(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patcher in (
            patch.object(predictions_module, "PREDICTIONS_DIR", Path(tmp.name)),
            patch.object(hub, "refresh_data_if_stale"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        hub._api_cache.clear()
        self.client = MagicMock()
        self.client.get_lineup.return_value = {
            "team_id": "t1", "period": 5, "total": 12.0,
            "starters": [{"id": "a", "slot": "M", "minutes": 70}, {"id": "b", "slot": "F", "minutes": 0}],
            "bench": [{"id": "c", "slot": "", "minutes": 90}],
            "injured_reserve": [],
        }
        predictions_module.predictions_path(5).write_text(json.dumps({"season": 2026, "players": {
            "a": {"position": "M", "fixtures": ["X"], "basis": "player", "scoring": {"M": {"per_min": 0.1, "clean_sheet": 1.0}}},
            "c": {"position": "D", "fixtures": ["X"], "basis": "player", "scoring": {"D": {"per_min": 0.2, "clean_sheet": 2.0}}},
        }}))

    def get(self, url):
        with patch.object(hub, "get_client", return_value=self.client):
            return hub.app.test_client().get(url)

    def test_returns_only_starters_with_their_predictions(self):
        body = self.get("/api/predicted-totals/5?teams=t1").get_json()
        starters = body["teams"]["t1"]
        self.assertEqual([p["id"] for p in starters], ["a", "b"])
        self.assertEqual(starters[0]["minutes"], 70)
        self.assertEqual(starters[0]["prediction"]["per_min"], 0.1)
        self.assertIsNone(starters[1]["prediction"])

    def test_week_without_predictions_never_calls_fantrax(self):
        body = self.get("/api/predicted-totals/6?teams=t1").get_json()
        self.assertEqual(body["teams"], {})
        self.client.get_lineup.assert_not_called()

    def test_lineups_are_cached_between_requests(self):
        self.get("/api/predicted-totals/5?teams=t1")
        self.get("/api/predicted-totals/5?teams=t1")
        self.assertEqual(self.client.get_lineup.call_count, 1)

    def test_fantrax_failure_is_an_error_response(self):
        self.client.get_lineup.side_effect = RuntimeError("expired")
        self.assertEqual(self.get("/api/predicted-totals/5?teams=t1").status_code, 502)


if __name__ == "__main__":
    unittest.main()

"""
The Gentlemen's Invitational: Fantasy Prem Web Application & API Server.
Directly integrated with the real Fantrax API League data (soccer.fantrax_wrapper).
"""

import os
import sys
import json
import base64
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any
from flask import Flask, jsonify, request, send_from_directory
import pandas as pd

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
SOCCER_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SOCCER_DIR not in sys.path:
    sys.path.insert(0, SOCCER_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import Fantrax SDK components
try:
    from fantrax_wrapper import (
        FantraxClient,
        FantasyScoringEngine,
        compute_optimal_lineup_score,
        calculate_manager_efficiency,
        calculate_median_standings,
        calculate_optimal_standings,
        compare_standings_vs_optimal,
    )
    FANTRAX_SDK_AVAILABLE = True
except ImportError as e:
    print(f"Warning: fantrax_wrapper not directly imported: {e}")
    FANTRAX_SDK_AVAILABLE = False

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
scoring_engine = FantasyScoringEngine() if FANTRAX_SDK_AVAILABLE else None

LEAGUE_ID = os.getenv("FANTRAX_LEAGUE_ID", "iku2an1nmryzcfa2")

# Hosted deployments pass the Fantrax login cookie (a binary pickle) base64-encoded in FANTRAX_COOKIE_B64,
# since environment variables can't hold binary. Decode it to a temp file that the sync reads.
if os.getenv("FANTRAX_COOKIE_B64"):
    _cookie_file = os.path.join(tempfile.gettempdir(), "fantraxloggedin.cookie")
    with open(_cookie_file, "wb") as f:
        f.write(base64.b64decode(os.environ["FANTRAX_COOKIE_B64"]))
    os.environ["FANTRAX_COOKIE_PATH"] = _cookie_file
COOKIE_PATH = os.getenv("FANTRAX_COOKIE_PATH") or os.path.join(PROJECT_ROOT, "fantraxloggedin.cookie")

# How long a Fantrax sync stays fresh before the next request for data.js triggers another.
SYNC_TTL_SECONDS = float(os.getenv("DATA_SYNC_TTL_MINUTES", "15")) * 60
_sync_lock = threading.Lock()
_last_sync = float("-inf")
# Next gameweek start/end returned by the last sync; data is stale from then on regardless of the TTL.
_next_boundary = None
# Gameweeks officially over as of the last sync; their lineups can no longer change.
_completed_gws = set()

# Lineups and squads fetched from Fantrax on demand: {key: (expires_at_monotonic, value)}.
LINEUP_TTL_FINAL_SECONDS = 24 * 60 * 60
LINEUP_TTL_LIVE_SECONDS = 2 * 60
SQUAD_TTL_SECONDS = 10 * 60
_api_cache: Dict[Any, Any] = {}
_api_cache_lock = threading.Lock()


def cached(key, ttl_seconds: float, fetch):
    """Return a cached value for key, calling fetch() when it is missing or expired."""
    now = time.monotonic()
    with _api_cache_lock:
        hit = _api_cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = fetch()
    with _api_cache_lock:
        _api_cache[key] = (now + ttl_seconds, value)
    return value


def get_client() -> FantraxClient:
    """Instantiate Fantrax client for the configured league."""
    return FantraxClient(league_id=LEAGUE_ID, cookie_path=COOKIE_PATH)


@app.route("/")
def index():
    """Serve main single-page application."""
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/data.js")
def serve_data():
    """Serve the league dataset, re-syncing from Fantrax first when it is stale."""
    refresh_data_if_stale()
    response = send_from_directory(BASE_DIR, "data.js")
    response.headers["Cache-Control"] = "no-cache"
    return response


def refresh_data_if_stale() -> None:
    """Re-run sync_data.main() when the last sync is older than DATA_SYNC_TTL_MINUTES, or a gameweek
    has started or ended since it ran.

    Each worker process syncs on its first request and then at most once per TTL. If a sync
    is already running, or Fantrax fails, the existing data.js is served unchanged.
    """
    global _last_sync, _next_boundary, _completed_gws

    def is_stale() -> bool:
        if time.monotonic() - _last_sync >= SYNC_TTL_SECONDS:
            return True
        return _next_boundary is not None and datetime.now(timezone.utc) >= _next_boundary

    if not FANTRAX_SDK_AVAILABLE or not is_stale():
        return
    if not _sync_lock.acquire(blocking=False):
        return
    try:
        if not is_stale():
            return
        import sync_data
        result = sync_data.main()
        _next_boundary = result["next_boundary"]
        _completed_gws = set(result["completed_gws"])
    except Exception as e:
        print(f"Warning: data sync failed, serving existing data.js: {e}")
    finally:
        # Also back off after a failure so a Fantrax outage doesn't trigger a sync on every request.
        _last_sync = time.monotonic()
        _sync_lock.release()


@app.route("/<path:filename>")
def serve_static(filename):
    """Serve static CSS, JS, images, or JSON data files."""
    return send_from_directory(BASE_DIR, filename)


# --- REST API ENDPOINTS POWERED BY FANTRAX WRAPPER ---

@app.route("/api/health", methods=["GET"])
def health_check():
    """System health check & SDK availability status."""
    cookie_exists = os.path.exists(COOKIE_PATH)
    return jsonify({
        "status": "healthy",
        "app": "The Gentlemen's Invitational League Hub",
        "season": "2026-2027",
        "fantrax_sdk_loaded": FANTRAX_SDK_AVAILABLE,
        "configured_league_id": LEAGUE_ID,
        "cookie_present": cookie_exists
    })


@app.route("/api/standings", methods=["GET"])
def get_live_standings():
    """Fetches real-time league standings directly from Fantrax API."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax SDK unavailable"}), 500
    try:
        client = get_client()
        table = client.get_league_table()
        return jsonify({
            "success": True,
            "league_id": LEAGUE_ID,
            "standings": table.reset_index().to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/efficiency", methods=["GET"])
def get_live_efficiency():
    """Fetches live manager lineup efficiency metrics directly from Fantrax."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax SDK unavailable"}), 500
    try:
        client = get_client()
        eff = client.get_league_manager_efficiency()
        return jsonify({
            "success": True,
            "efficiency": eff.reset_index().to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/optimal-standings", methods=["GET"])
def get_live_optimal():
    """Fetches live optimal standings table directly from Fantrax."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax SDK unavailable"}), 500
    try:
        client = get_client()
        opt = client.get_optimal_standings()
        return jsonify({
            "success": True,
            "optimal_standings": opt.reset_index().to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/median-standings", methods=["GET"])
def get_live_median():
    """Fetches live standings against median directly from Fantrax."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax SDK unavailable"}), 500
    try:
        client = get_client()
        matchups = client.get_matchups(through_week=38, as_dataframe=True)
        median = calculate_median_standings(matchups)
        return jsonify({
            "success": True,
            "median_standings": median.reset_index().to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/lineups/<int:week>", methods=["GET"])
def get_lineups(week: int):
    """Starting lineups and benches for one or more teams in a gameweek: /api/lineups/7?teams=id1,id2"""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax SDK unavailable"}), 500
    team_ids = [t for t in request.args.get("teams", "").split(",") if t][:4]
    if not team_ids or not 1 <= week <= 38:
        return jsonify({"error": "Pass a gameweek from 1 to 38 and ?teams=<fantrax team ids>"}), 400
    refresh_data_if_stale()
    ttl = LINEUP_TTL_FINAL_SECONDS if week in _completed_gws else LINEUP_TTL_LIVE_SECONDS
    try:
        client = get_client()
        lineups = {t: cached(("lineup", week, t), ttl, lambda t=t: client.get_lineup(t, week)) for t in team_ids}
        return jsonify({"week": week, "final": week in _completed_gws, "lineups": lineups})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/squad/<team_id>", methods=["GET"])
def get_squad(team_id: str):
    """A team's current players with season-to-date fantasy points."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax SDK unavailable"}), 500
    try:
        squad = cached(("squad", team_id), SQUAD_TTL_SECONDS, lambda: get_client().get_squad(team_id))
        return jsonify({"team_id": team_id, "players": squad})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/matchups/<int:week>", methods=["GET"])
def get_live_gameweek_matchups(week: int):
    """Fetches matchups for a specific matchweek directly from Fantrax."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax SDK unavailable"}), 500
    try:
        client = get_client()
        matchups = client.get_matchups(through_week=week, as_dataframe=True)
        gw_matchups = matchups[matchups["week"] == week]
        return jsonify({
            "success": True,
            "week": week,
            "matchups": gw_matchups.to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/scoring/calculate", methods=["POST"])
def calculate_score():
    """Calculates FPts and Adjusted FPts (aFPts) using the official FantasyScoringEngine."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Fantrax Scoring Engine SDK unavailable"}), 500

    payload = request.get_json() or {}
    position = payload.get("position", "M").upper()
    stats = payload.get("stats", {})

    try:
        fpts = scoring_engine.calculate_fantasy_score(stats, position)
        afpts = scoring_engine.calculate_adjusted_fantasy_score(stats, position)
        pos_rules = scoring_engine.rules.get(position, {})
        breakdown = {k: stats[k] * pos_rules.get(k, 0) for k in stats if k in pos_rules}

        return jsonify({
            "position": position,
            "raw_stats": stats,
            "fantasy_points": fpts,
            "adjusted_fantasy_points": afpts,
            "scoring_breakdown": breakdown
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/analytics/optimal-lineup", methods=["POST"])
def optimal_lineup():
    """Computes optimal lineup score from a player score pool using compute_optimal_lineup_score."""
    if not FANTRAX_SDK_AVAILABLE:
        return jsonify({"error": "Analytics Engine SDK unavailable"}), 500

    payload = request.get_json() or {}
    g_scores = [float(x) for x in payload.get("g_scores", [])]
    d_scores = [float(x) for x in payload.get("d_scores", [])]
    m_scores = [float(x) for x in payload.get("m_scores", [])]
    f_scores = [float(x) for x in payload.get("f_scores", [])]

    max_score = compute_optimal_lineup_score(g_scores, d_scores, m_scores, f_scores)
    return jsonify({
        "max_optimal_score": max_score,
        "roster_breakdown": {
            "G_count": len(g_scores),
            "D_count": len(d_scores),
            "M_count": len(m_scores),
            "F_count": len(f_scores)
        }
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"============================================================")
    print(f" ⚽ The Gentlemen's Invitational Fantasy Prem Web Server ⚽ ")
    print(f" Connected to League ID: {LEAGUE_ID}")
    print(f" Server running at: http://localhost:{port}")
    print(f" SDK Status: {'Active' if FANTRAX_SDK_AVAILABLE else 'Mock'}")
    print(f"============================================================")
    app.run(host="0.0.0.0", port=port, debug=True)

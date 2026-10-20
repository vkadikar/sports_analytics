"""
The Gentlemen's Invitational: Fantasy Prem Web Application & API Server.
Directly integrated with the real Fantrax API League data (soccer.fantrax_wrapper).
"""

import os
import sys
import json
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
COOKIE_PATH = os.path.join(PROJECT_ROOT, "fantraxloggedin.cookie")


def get_client() -> FantraxClient:
    """Instantiate Fantrax client for the configured league."""
    return FantraxClient(league_id=LEAGUE_ID, cookie_path=COOKIE_PATH)


@app.route("/")
def index():
    """Serve main single-page application."""
    return send_from_directory(BASE_DIR, "index.html")


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

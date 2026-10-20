# ⚽ The Gentlemen’s Invitational — Fantasy Prem 2026-27 Web Hub

Official interactive web headquarters and analytics dashboard for **The Gentlemen’s Invitational Fantasy Premier League (2026–27)**, founded and commissioned by Shayan Hussain & Varun Kadikar.

---

## 🌟 Key Features

1. **🏆 Official & Optimal Standings Hub**:
   - **Official League Table**: Real-time 14-team table highlighting Champions League spots (1st–5th) and the Relegation/IHOP Penalty zone (14th).
   - **Manager Lineup Efficiency Index**: Powered by `soccer.fantrax_wrapper.analytics` to compare actual points scored against the optimal starting XI maximum possible score.
   - **Standings vs Weekly Median**: Evaluates squad strength independent of schedule luck.

2. **⚔️ Matchup Center & 14×14 Head-to-Head Matrix**:
   - Weekly scorecards with Gameweek switcher (GW 1–38).
   - Interactive 14×14 Head-to-Head series grid displaying career rivalry records.

3. **⭐ 2026–27 Champions League**:
   - 6-team group stage table and designated matchday schedule (GW 6, 11, 16, 21, 26).
   - Knockout stage format (Two-legged aggregate Semis on GW 31 & 33, Final on GW 36).

4. **🏆 2026–27 Lingineni Cup**:
   - 14-team single-elimination tournament bracket with top-4 byes to the Quarter-Finals.

5. **💰 $1,400 Prize Pool Distribution**:
   - Complete breakdown ($400 Regular Season Champion, $200 Champions League, $170 Lingineni Cup, $150 2nd, $100 3rd, $380 Weekly High Scores).

6. **📜 League History & Archives**:
   - All-Time leaderboard for all 18 historical participants (Pts/Week, W/D/L, Total Pts).
   - All-Time Career Prize Money leaderboard and accolades.
   - Season archives: 2025–26, 2024–25, and 2023–24.
   - Wall of Disgrace & Relegation Memorial (Drew, Henry/hdiamondpott, Arman, Linguini FC).

7. **🥞 24-Hour IHOP Challenge Penalty Calculator**:
   - Real-time pancake slider calculating remaining hours inside IHOP for the last-place finisher.

8. **📊 Scoring Matrix & Interactive Fantasy Simulator**:
   - Official rules for Goalkeepers (G), Defenders (D), Midfielders (M), and Forwards (F).
   - Stat simulator connected to Python scoring engine `/api/scoring/calculate`.

9. **👔 14 Manager Dossiers**:
   - City origins, career records, trophy counts, and bios.

---

## 🚀 Running Locally

```bash
# Start the web server
python3 soccer/league_hub/app.py
```
Open **`http://localhost:8080`** in your browser.

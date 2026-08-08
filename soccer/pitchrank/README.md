# PitchRank FPL - Fantasy Premier League Draft Ranker

PitchRank FPL is an interactive pairwise draft tier list generator and matchup ranker for Fantasy Premier League draft preparation.

## 🚀 Features

- **Position-Specific Tier Lists**: Full player pools for Forwards (142), Midfielders (247), Defenders (228), and Goalkeepers (81).
- **Binary Insertion Algorithm**: Fast head-to-head duels that minimize comparison choices (~4-5 choices per player).
- **Skip Unfamiliar Players**: Skip any player with hotkey `S` or `↓`. Skipped players are kept in a separate board section and can be re-ranked anytime.
- **Multi-Sheet Excel Export**: One-click **Export Excel (.xlsx)** generates a single workbook containing separate sheets for **Forwards**, **Midfielders**, **Defenders**, and **Goalkeepers**.
- **State Persistence**: Progress automatically saves in browser `localStorage`.

---

## 🌐 Deploying to Render (Shareable Web App Link)

Render (https://render.com) provides free web hosting for web applications.

### Option A: Deploy via GitHub (Recommended)
1. Push this repository or the `soccer/pitchrank` folder to GitHub.
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** -> **Web Service**.
4. Connect your GitHub repository.
5. Set the following settings:
   - **Root Directory**: `soccer/pitchrank` (or `./` if deploying from a repository created directly in `pitchrank`)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
6. Click **Create Web Service**. Render will build and deploy your live URL (e.g. `https://pitchrank-fpl.onrender.com`) that you can share with friends!

### Option B: Deploy via Render Blueprint (`render.yaml`)
1. In Render, select **New +** -> **Blueprint**.
2. Select your repository. Render will automatically read `render.yaml` and provision the web service!

---

## 💻 Running Locally

To run locally on your machine:
```bash
python3 soccer/pitchrank/app.py
```
Open [http://localhost:8000](http://localhost:8000) in your web browser.

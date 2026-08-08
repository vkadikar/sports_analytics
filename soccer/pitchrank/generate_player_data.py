import os
import json
import pandas as pd

def generate_player_data():
    # Path to draft_data.csv in soccer/research/draft_data.csv
    base_dir = os.path.abspath(os.path.dirname(__file__))
    csv_path = os.path.abspath(os.path.join(base_dir, "..", "research", "draft_data.csv"))
    json_path = os.path.join(base_dir, "players_data.json")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Cannot find source data at {csv_path}")

    df = pd.read_csv(csv_path)

    # Clean up duplicate adp columns if present
    if "adp.1" in df.columns:
        df = df.drop(columns=["adp.1"])
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    # Ensure numeric fields
    df["adp"] = pd.to_numeric(df["adp"], errors="coerce").fillna(999.0)
    df["projected_pts"] = pd.to_numeric(df["projected_pts"], errors="coerce").fillna(0.0)
    df["2025_total_pts"] = pd.to_numeric(df["2025_total_pts"], errors="coerce").fillna(0.0)
    df["2024_total_pts"] = pd.to_numeric(df["2024_total_pts"], errors="coerce").fillna(0.0)

    # Clean text columns
    df["name"] = df["name"].astype(str).str.strip()
    df["team_name"] = df["team_name"].astype(str).str.strip()
    df["position"] = df["position"].astype(str).str.strip().str.upper()

    positions = ["F", "M", "D", "G"]
    segmented_data = {}

    for pos in positions:
        pos_df = df[df["position"] == pos].sort_values(by="adp", ascending=True)
        players_list = []
        for idx, row in pos_df.iterrows():
            players_list.append({
                "id": str(idx),
                "name": row["name"],
                "team": row["team_name"],
                "position": row["position"],
                "adp": round(float(row["adp"]), 2),
                "projected_pts": round(float(row["projected_pts"]), 1),
                "pts_2025": round(float(row["2025_total_pts"]), 1),
                "pts_2024": round(float(row["2024_total_pts"]), 1),
            })
        segmented_data[pos] = players_list
        print(f"Position {pos}: Extracted all {len(players_list)} players by ADP.")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(segmented_data, f, indent=2)

    print(f"\nSaved all player dataset to: {json_path}")

if __name__ == "__main__":
    generate_player_data()

import os
import sys
from flask import Flask, send_from_directory

# Get absolute path to the directory containing this script
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(BASE_DIR, filename)

if __name__ == "__main__":
    # Bind to PORT environment variable (Render sets this dynamically, defaults to 8000 locally)
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting PitchRank FPL Web Server on port {port}...")
    app.run(host="0.0.0.0", port=port)

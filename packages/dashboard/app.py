"""Standalone runner — thin wrapper around glasspipe._dashboard."""
from glasspipe._dashboard import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3000, debug=True, use_reloader=False)

"""Local GlassPipe dashboard — Flask skeleton (Day 1)."""
from flask import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return "GlassPipe dashboard — Day 1"


if __name__ == "__main__":
    app.run(port=5050, debug=True)

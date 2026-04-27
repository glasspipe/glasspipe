"""Hosted GlassPipe share API — Flask skeleton (Day 1). Deploys to Railway later."""
from flask import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return "GlassPipe API — Day 1"


if __name__ == "__main__":
    app.run(port=5051, debug=True)

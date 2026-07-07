import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _config():
    return json.loads((ROOT / "vercel.json").read_text())


def test_vercel_keeps_landing_page_as_static_output():
    config = _config()

    assert config["outputDirectory"] == "packages/web"


def test_vercel_routes_share_api_and_viewer_to_flask_function():
    config = _config()
    rewrites = {
        rewrite["source"]: rewrite["destination"]
        for rewrite in config["rewrites"]
    }

    assert rewrites == {
        "/health": "/api/index",
        "/v1/:path*": "/api/index",
        "/t/:path*": "/api/index",
        "/static/:path*": "/api/index",
    }


def test_vercel_function_includes_viewer_templates_and_assets():
    config = _config()

    assert config["functions"]["api/index.py"]["includeFiles"] == (
        "packages/api/{templates,static}/**"
    )


def test_vercel_root_requirements_match_share_api_requirements():
    assert (ROOT / "requirements.txt").read_text() == (
        ROOT / "packages" / "api" / "requirements.txt"
    ).read_text()

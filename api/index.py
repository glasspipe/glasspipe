"""Vercel Python Function entrypoint for the existing Flask share API."""
import sys
from pathlib import Path


API_DIR = Path(__file__).resolve().parents[1] / "packages" / "api"
sys.path.insert(0, str(API_DIR))

from app import app  # noqa: E402

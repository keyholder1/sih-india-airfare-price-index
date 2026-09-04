"""Vercel Python serverless entrypoint.

Vercel's Python runtime expects a module that exports an ASGI/WSGI `app`
object -- this just re-exports api.main's FastAPI app, after putting the
repo root and src/ on sys.path so the src-layout imports used throughout
the codebase (``from src.engine import db``, ``from scraper.config import
ScraperConfig``, ``import data_quality``, etc.) resolve the same way they
do locally. Locally this works because the project is installed with
``pip install -e .`` (setuptools maps package roots to src/, see
pyproject.toml's ``[tool.setuptools.packages.find] where = ["src"]``) and
because pytest's own ``pythonpath = ["src", "."]`` setting does the same
for tests -- Vercel's build only runs ``pip install -r requirements.txt``,
which does neither, so this file does it explicitly instead.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT, _REPO_ROOT / "src"):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from api.main import app  # noqa: E402

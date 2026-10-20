"""Vercel entrypoint for the Arsenal API.

Public traffic arrives as `/api/...`. The service rewrite in `vercel.json`
strips that prefix, and `AcceptApiPrefix` strips it again if it is still
present. `uvicorn app.main:app` on a laptop stays unprefixed.
"""

from app.main import app

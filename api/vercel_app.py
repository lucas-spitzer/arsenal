"""Vercel entrypoint for the Arsenal API.

Public traffic arrives as `/api/...` on the same host as the Vite app.
`uvicorn app.main:app` on a laptop stays unprefixed.
"""

from fastapi import FastAPI

from app.main import app as arsenal_api

app = FastAPI(title="Arsenal")
app.mount("/api", arsenal_api)

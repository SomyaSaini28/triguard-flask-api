"""Small server-side security helpers shared by browser routes."""

from __future__ import annotations

import secrets

from flask import request, session


def csrf_token() -> str:
    """Return a session-bound anti-forgery token for browser form submissions."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_is_valid() -> bool:
    """Validate either a form token or an XMLHttpRequest header token."""
    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token")
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))

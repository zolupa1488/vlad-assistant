"""Google OAuth credentials builder, using a stored long-lived refresh_token.

Once we have a refresh_token (issued by `scripts/google_oauth_setup.py`),
the client can mint short-lived access_tokens on every API call, forever.
"""

from __future__ import annotations

from google.oauth2.credentials import Credentials

from src.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_credentials() -> Credentials:
    if not (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_refresh_token
    ):
        raise RuntimeError(
            "Google OAuth env vars are missing. "
            "Need GOOGLE_OAUTH_CLIENT_ID / _SECRET / _REFRESH_TOKEN."
        )

    return Credentials(
        token=None,
        refresh_token=settings.google_oauth_refresh_token,
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )

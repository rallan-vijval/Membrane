"""Read-only Gmail access for explicitly selected messages. No mailbox sync, no send/modify scopes.

Credentials are a Google OAuth client plus a refresh token granted for gmail.readonly, all kept in
the local .env. Tokens never leave this module and are never returned by the API.
"""
import time
from threading import Lock

import httpx

from ..common import Problem

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
HEADERS = ("Subject", "From", "Date")


class Gmail:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self._http = httpx.Client(timeout=settings.model_timeout_seconds, transport=transport)
        self._lock = Lock()
        self._access, self._expires = None, 0.0

    def configured(self):
        s = self.settings
        return bool(s.gmail_enabled and s.gmail_client_id and s.gmail_client_secret.get_secret_value()
                    and s.gmail_refresh_token.get_secret_value())

    def require(self):
        if not self.settings.gmail_enabled:
            raise Problem("gmail_disabled", "Gmail import is disabled; set GMAIL_ENABLED=true", 503)
        if not self.configured():
            raise Problem("gmail_unavailable", "Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN (run scripts/gmail_authorize.py)", 503)

    def _token(self):
        with self._lock:
            if self._access and time.time() < self._expires - 60:
                return self._access
            s = self.settings
            try:
                response = self._http.post(TOKEN_URL, data={"grant_type": "refresh_token", "client_id": s.gmail_client_id,
                    "client_secret": s.gmail_client_secret.get_secret_value(),
                    "refresh_token": s.gmail_refresh_token.get_secret_value()})
            except httpx.HTTPError:
                raise Problem("gmail_unavailable", "Could not reach Google to refresh Gmail access", 503)
            if response.status_code != 200:
                raise Problem("gmail_unavailable", "Google rejected the Gmail credentials; re-run scripts/gmail_authorize.py", 503)
            body = response.json()
            self._access, self._expires = body["access_token"], time.time() + int(body.get("expires_in", 3600))
            return self._access

    def _get(self, path, params=None):
        self.require()
        try:
            response = self._http.get(f"{API}/{path}", params=params or {}, headers={"Authorization": f"Bearer {self._token()}"})
        except httpx.HTTPError:
            raise Problem("gmail_error", "Gmail request failed; try again", 502)
        if response.status_code == 404:
            raise Problem("not_found", "Gmail message or thread not found", 404)
        if response.status_code in (401, 403):
            raise Problem("gmail_unavailable", "Gmail access was refused; check the read-only grant", 503)
        if response.status_code != 200:
            raise Problem("gmail_error", "Gmail returned an unexpected response", 502)
        return response.json()

    def account(self):
        return self._get("profile").get("emailAddress", "")

    def search(self, query, limit):
        """Metadata only: nothing is stored and no bodies are fetched until a message is imported."""
        found = self._get("messages", {"q": query, "maxResults": limit}).get("messages", [])
        items = []
        for ref in found[:limit]:
            meta = self._get(f"messages/{ref['id']}", [("format", "metadata"), *(("metadataHeaders", h) for h in HEADERS)])
            headers = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
            items.append({"message_id": meta["id"], "thread_id": meta.get("threadId", ""),
                          "subject": headers.get("subject", ""), "sender": headers.get("from", ""),
                          "date": headers.get("date", ""), "snippet": meta.get("snippet", "")})
        return items

    def message(self, message_id):
        return self._get(f"messages/{message_id}", {"format": "full"})

    def thread(self, thread_id):
        return self._get(f"threads/{thread_id}", {"format": "full"}).get("messages", [])

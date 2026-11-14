"""One-time local consent for read-only Gmail access. Writes GMAIL_REFRESH_TOKEN to .env.

Needs GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET from a Google OAuth "Desktop app" client in .env.
Run: python -m scripts.gmail_authorize   (opens a browser; the token is never printed)
"""
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from backend.app.config import ROOT, Settings
from backend.app.integrations.gmail import SCOPE, TOKEN_URL


def save(token):
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(("GMAIL_REFRESH_TOKEN=", "GMAIL_ENABLED="))]
    lines += ["GMAIL_ENABLED=true", f"GMAIL_REFRESH_TOKEN={token}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    cfg = Settings()
    if not cfg.gmail_client_id or not cfg.gmail_client_secret.get_secret_value():
        raise SystemExit("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env first.")
    state, result = secrets.token_urlsafe(24), {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [""])[0] == state:
                result.update(code=query.get("code", [""])[0], error=query.get("error", [""])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Membrane: you can close this tab and return to the terminal.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"client_id": cfg.gmail_client_id,
        "redirect_uri": redirect, "response_type": "code", "scope": SCOPE, "access_type": "offline",
        "prompt": "consent", "state": state})
    print("Approve read-only Gmail access in your browser. If it does not open, visit:\n" + url)
    webbrowser.open(url)
    while not result:
        server.handle_request()
    if not result.get("code"):
        raise SystemExit("Consent was not granted: " + (result.get("error") or "no code returned"))
    response = httpx.post(TOKEN_URL, data={"grant_type": "authorization_code", "code": result["code"],
        "client_id": cfg.gmail_client_id, "client_secret": cfg.gmail_client_secret.get_secret_value(),
        "redirect_uri": redirect}, timeout=30)
    token = response.json().get("refresh_token") if response.status_code == 200 else None
    if not token:
        raise SystemExit("Google did not return a refresh token; check the client type is 'Desktop app'.")
    save(token)
    print("Saved GMAIL_REFRESH_TOKEN and GMAIL_ENABLED=true to .env. Restart the backend.")


if __name__ == "__main__":
    main()

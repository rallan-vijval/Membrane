"""Gmail import: Google is replaced by an explicit in-test transport; no network, no real mailbox."""
import base64
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.email_source import parse, render_png, render_text
from backend.app.integrations.gmail import Gmail
from backend.app.main import create_app


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def message(mid, body, subject="Refund exception", html=False, attachment=None):
    part = {"mimeType": "text/html" if html else "text/plain", "body": {"data": b64(body)}}
    parts = [part] + ([{"mimeType": "application/pdf", "filename": attachment, "body": {"attachmentId": "a1"}}] if attachment else [])
    return {"id": mid, "threadId": "t1", "snippet": body[:40], "payload": {"mimeType": "multipart/mixed",
        "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": "Supervisor <sup@example.test>"},
                    {"name": "Date", "value": "Sat, 14 Nov 2026 10:00:00 -0500"}], "parts": parts}}


BODY = "For order 4821, customer customer-4821, exception exc-4821: refund approved without return."
MAIL = {"m1": message("m1", BODY, attachment="note.pdf"), "m2": message("m2", "<p>Thanks,<br>noted.</p><script>x()</script>", html=True)}


def google(request):
    calls.append(request)
    path = request.url.path
    if request.url.host == "oauth2.googleapis.com":
        form = parse_qs(request.content.decode())
        return httpx.Response(200 if form["refresh_token"] == ["refresh-ok"] else 400, json={"access_token": "access", "expires_in": 3600})
    assert request.headers["Authorization"] == "Bearer access"
    if path.endswith("/profile"):
        return httpx.Response(200, json={"emailAddress": "reviewer@example.test"})
    if path.endswith("/messages"):
        return httpx.Response(200, json={"messages": [{"id": "m1"}, {"id": "m2"}]})
    if path.endswith("/threads/t1"):
        return httpx.Response(200, json={"messages": list(MAIL.values())})
    mid = path.rsplit("/", 1)[1]
    return httpx.Response(200, json=MAIL[mid]) if mid in MAIL else httpx.Response(404, json={})


calls = []


@pytest.fixture
def client(env):
    cfg, store, provider, service, _ = env
    calls.clear()
    cfg = cfg.model_copy(update={"gmail_enabled": True, "gmail_client_id": "client",
        "gmail_client_secret": Settings(_env_file=None, gmail_client_secret="secret").gmail_client_secret,
        "gmail_refresh_token": Settings(_env_file=None, gmail_refresh_token="refresh-ok").gmail_refresh_token})
    provider.extract_email = lambda text: ({"extracted_text": text, "quotation": "refund approved without return",
        "proposed_text": "Order 4821 may be refunded without return.",
        "proposed_scope": {"kind": "order", "order_id": "4821", "customer_id": "customer-4821", "exception_id": "exc-4821"}},
        {"model": "TEST ONLY"})
    return TestClient(create_app(cfg, store, provider, gmail=Gmail(cfg, httpx.MockTransport(google)))), store


def test_parse_prefers_plain_text_strips_html_and_names_attachments():
    plain, html = parse(MAIL["m1"]), parse(MAIL["m2"])
    assert plain["body"] == BODY and plain["attachments"] == ["note.pdf"]
    assert html["body"] == "Thanks,\nnoted."
    text = render_text([plain, html], 12000)
    assert "Attachments (not read): note.pdf" in text and "next message in thread" in text
    assert render_text([plain], 500).endswith("not included.]") is False
    assert len(render_text([{**plain, "body": "x" * 9000}], 500)) == 500
    assert render_png(text)[:4] == b"\x89PNG"


def test_status_and_search_return_metadata_only(client):
    api, _ = client
    assert api.get("/api/gmail/status").json() == {"status": "ready", "reason": "Read-only Gmail access verified", "account": "reviewer@example.test"}
    items = api.get("/api/gmail/messages", params={"q": "refund"}).json()["items"]
    assert [i["message_id"] for i in items] == ["m1", "m2"] and items[0]["subject"] == "Refund exception"
    assert "body" not in items[0]
    assert all("format=full" not in str(c.url) for c in calls)
    assert api.get("/api/health").json()["gmail"]["status"] == "degraded"


def test_import_message_becomes_untrusted_stageable_source(client):
    api, store = client
    source = api.post("/api/gmail/messages/m1/import")
    assert source.status_code == 201
    body = source.json()
    assert body["trust"] == "untrusted" and body["mime_type"] == "message/rfc822"
    assert BODY in body["extracted_text"] and body["quotation"] in body["extracted_text"]
    assert body["provenance"]["channel"] == "gmail" and body["provenance"]["message_ids"] == ["m1"]
    assert body["provenance"]["account"] == "reviewer@example.test"
    assert "secret" not in source.text and "refresh-ok" not in source.text
    image = api.get(body["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    staged = api.post("/api/candidates", json={"source_id": body["source_id"], "text": body["proposed_text"],
        "scope": body["proposed_scope"], "base_version_id": store.active()["version_id"]})
    assert staged.status_code == 201 and staged.json()["status"] == "staged"


def test_import_thread_keeps_every_message(client):
    api, _ = client
    body = api.post("/api/gmail/threads/t1/import").json()
    assert body["provenance"]["message_ids"] == ["m1", "m2"] and body["provenance"]["import_kind"] == "thread"
    assert "noted." in body["extracted_text"]


def test_missing_message_bad_id_and_disabled(client, env):
    api, _ = client
    assert api.post("/api/gmail/messages/nope/import").status_code == 404
    assert api.post("/api/gmail/messages/bad%20id!/import").status_code == 422
    cfg, store, provider, *_ = env
    off = TestClient(create_app(cfg, store, provider))
    assert off.get("/api/gmail/status").json()["status"] == "disabled"
    assert off.get("/api/gmail/messages").json()["error"]["code"] == "gmail_disabled"
    assert off.get("/api/health").json()["gmail"]["status"] == "disabled"


def test_rejected_credentials_are_reported_without_leaking(env):
    cfg, store, provider, *_ = env
    cfg = cfg.model_copy(update={"gmail_enabled": True, "gmail_client_id": "client",
        "gmail_client_secret": Settings(_env_file=None, gmail_client_secret="secret").gmail_client_secret,
        "gmail_refresh_token": Settings(_env_file=None, gmail_refresh_token="revoked").gmail_refresh_token})
    api = TestClient(create_app(cfg, store, provider, gmail=Gmail(cfg, httpx.MockTransport(google))))
    status = api.get("/api/gmail/status")
    assert status.json()["status"] == "unavailable" and "revoked" not in status.text


def test_extract_email_keeps_text_authoritative_and_drops_inexact_quote(env):
    from backend.app.provider import Provider
    cfg = env[0]
    provider = Provider(cfg)
    scope = {"kind": "preference", "order_id": None, "customer_id": None, "exception_id": None}
    provider._response = lambda *a, **k: ({"quotation": "not in the email", "proposed_text": "p", "proposed_scope": scope}, {"id": "r1"}, 1)
    data, provenance = provider.extract_email("the real email")
    assert data["extracted_text"] == "the real email" and data["quotation"] == ""
    assert provenance["prompt_version"] == "extract-email-v1"


# ---- App-password (IMAP) client: imaplib is replaced by an explicit in-test connection. ----

RAW = {b"11": (b"9001", b"7001", b"Subject: Refund exception\r\nFrom: Supervisor <sup@example.test>\r\nDate: Sat, 14 Nov 2026 10:00:00 -0500\r\n"
                                 b"Content-Type: text/plain; charset=utf-8\r\n\r\n" + BODY.encode() + b"\r\n"),
       b"12": (b"9002", b"7001", b"Subject: Re: Refund exception\r\nFrom: Agent <agent@example.test>\r\nDate: Sat, 14 Nov 2026 11:00:00 -0500\r\n"
                                 b"Content-Type: text/html; charset=utf-8\r\n\r\n<p>Thanks,<br>noted.</p>\r\n")}


class FakeImap:
    log = []

    def __init__(self, password="abcdefghijklmnop"):
        self.password, self.literal = password, None

    def login(self, user, password):
        import imaplib
        self.log.append(("login", user))
        if password != self.password:
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        return "OK", [b"ok"]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']

    def select(self, folder, readonly=False):
        self.log.append(("select", folder, readonly))
        return "OK", [b"2"]

    def uid(self, command, *args):
        literal, self.literal = self.literal, None
        self.log.append((command, args, literal))
        if command == "SEARCH":
            if args[0] == "X-GM-MSGID":
                return "OK", [b" ".join(u for u, r in RAW.items() if r[0].decode() == args[1])]
            if args[0] == "X-GM-THRID":
                return "OK", [b" ".join(u for u, r in RAW.items() if r[1].decode() == args[1])]
            return "OK", [b"11 12"]
        out = []
        for uid in args[0].encode().split(b","):
            mid, tid, raw = RAW[uid]
            payload = raw.split(b"\r\n\r\n")[0] + b"\r\n\r\n" if "HEADER" in args[1] else raw
            out += [(b"1 (X-GM-THRID " + tid + b" X-GM-MSGID " + mid + b" UID " + uid + b" BODY[] {%d}" % len(payload), payload), b")"]
        return "OK", out

    def logout(self):
        self.log.append(("logout",))


@pytest.fixture
def imap(env):
    from backend.app.integrations.gmail_imap import GmailImap
    cfg, store, provider, *_ = env
    FakeImap.log = []
    cfg = cfg.model_copy(update={"gmail_enabled": True, "gmail_address": "reviewer@example.test",
        "gmail_app_password": Settings(_env_file=None, gmail_app_password="abcd efgh ijkl mnop").gmail_app_password})
    provider.extract_email = lambda text: ({"extracted_text": text, "quotation": "", "proposed_text": "p",
        "proposed_scope": {"kind": "preference", "order_id": None, "customer_id": None, "exception_id": None}}, {"model": "TEST ONLY"})
    return TestClient(create_app(cfg, store, provider, gmail=GmailImap(cfg, FakeImap))), cfg


def test_imap_search_is_read_only_headers_only_and_newest_first(imap):
    api, _ = imap
    assert api.get("/api/gmail/status").json()["account"] == "reviewer@example.test"
    items = api.get("/api/gmail/messages", params={"q": "refund café"}).json()["items"]
    assert [(i["message_id"], i["thread_id"], i["subject"]) for i in items] == [("9002", "7001", "Re: Refund exception"), ("9001", "7001", "Refund exception")]
    selects = [e for e in FakeImap.log if e[0] == "select"]
    assert selects and all(e == ("select", '"[Gmail]/All Mail"', True) for e in selects)
    search = next(e for e in FakeImap.log if e[0] == "SEARCH")
    assert search[1] == ("CHARSET", "UTF-8", "X-GM-RAW") and search[2] == "refund café".encode()
    fetches = [e for e in FakeImap.log if e[0] == "FETCH"]
    assert fetches and all("PEEK" in e[1][1] and "HEADER.FIELDS" in e[1][1] for e in fetches)
    assert not any(e[0] in ("STORE", "COPY", "EXPUNGE", "APPEND") for e in FakeImap.log)


def test_imap_import_message_and_thread(imap):
    api, _ = imap
    one = api.post("/api/gmail/messages/9001/import")
    assert one.status_code == 201 and BODY in one.json()["extracted_text"]
    assert one.json()["provenance"]["message_ids"] == ["9001"] and "abcd" not in one.text
    thread = api.post("/api/gmail/threads/7001/import").json()
    assert thread["provenance"]["message_ids"] == ["9001", "9002"] and "Thanks,\nnoted." in thread["extracted_text"]
    assert all("BODY.PEEK[]" in e[1][1] for e in FakeImap.log if e[0] == "FETCH")
    assert api.post("/api/gmail/messages/9999/import").status_code == 404
    assert api.post("/api/gmail/messages/abc/import").status_code == 404
    assert not any(e[0] == "SEARCH" and "abc" in e[1] for e in FakeImap.log)


def test_imap_wrong_password_and_factory(imap, env):
    from backend.app.integrations.gmail import Gmail, make_gmail
    from backend.app.integrations.gmail_imap import GmailImap
    _, cfg = imap
    bad = GmailImap(cfg, lambda: FakeImap("different"))
    with pytest.raises(Exception) as caught:
        bad.account()
    assert caught.value.code == "gmail_unavailable" and "abcd" not in caught.value.message
    assert isinstance(make_gmail(cfg), GmailImap) and isinstance(make_gmail(env[0]), Gmail)

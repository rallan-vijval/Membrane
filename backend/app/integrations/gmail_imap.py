"""Gmail through IMAP with an app password: no Google Cloud project needed.

An app password is not scoped, so read-only is enforced here: the mailbox is always opened with
readonly=True and bodies are fetched with BODY.PEEK, which never marks mail as read. Nothing is
written, moved or deleted. The password stays in the local .env and is never returned by the API.
"""
import imaplib
import re
from contextlib import contextmanager
from email import message_from_bytes, policy

from ..common import Problem
from ..email_source import parse_rfc822

HOST = "imap.gmail.com"
META = "(X-GM-MSGID X-GM-THRID BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])"
FULL = "(X-GM-MSGID X-GM-THRID BODY.PEEK[])"
MAX_THREAD = 20


def _records(data):
    """imaplib FETCH data -> [(attribute text, literal bytes)], tolerating attributes after the literal."""
    out = []
    for item in data or []:
        if isinstance(item, tuple):
            out.append([item[0], item[1]])
        elif isinstance(item, bytes) and out:
            out[-1][0] += b" " + item
    return out


def _ids(meta):
    msg, thread = re.search(rb"X-GM-MSGID (\d+)", meta), re.search(rb"X-GM-THRID (\d+)", meta)
    return (msg.group(1).decode() if msg else "", thread.group(1).decode() if thread else "")


class GmailImap:
    def __init__(self, settings, connect=None):
        self.settings = settings
        self._connect = connect or (lambda: imaplib.IMAP4_SSL(HOST, 993, timeout=settings.model_timeout_seconds))

    def configured(self):
        s = self.settings
        return bool(s.gmail_enabled and s.gmail_address and s.gmail_app_password.get_secret_value())

    def require(self):
        if not self.settings.gmail_enabled:
            raise Problem("gmail_disabled", "Gmail import is disabled; set GMAIL_ENABLED=true", 503)
        if not self.configured():
            raise Problem("gmail_unavailable", "Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD", 503)

    @contextmanager
    def _mailbox(self):
        self.require()
        conn = None
        try:
            try:
                conn = self._connect()
            except OSError:
                raise Problem("gmail_error", "Could not reach Gmail; try again", 502)
            try:
                # App passwords are displayed in groups of four; the spaces are not part of them.
                conn.login(self.settings.gmail_address, self.settings.gmail_app_password.get_secret_value().replace(" ", ""))
            except imaplib.IMAP4.error:
                raise Problem("gmail_unavailable", "Gmail rejected the address or app password", 503)
            try:
                folder = "INBOX"
                status, listing = conn.list()
                for line in (listing or []) if status == "OK" else []:
                    found = re.match(rb'\(([^)]*)\) "[^"]*" (.+)$', line or b"")
                    if found and b"\\All" in found.group(1):
                        folder = found.group(2).decode()
                if conn.select(folder, readonly=True)[0] != "OK":
                    raise Problem("gmail_error", "Could not open the mailbox read-only", 502)
                yield conn
            except (imaplib.IMAP4.error, OSError):
                raise Problem("gmail_error", "Gmail request failed; try again", 502)
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    @staticmethod
    def _uids(conn, *criteria, literal=None):
        if literal is not None:
            conn.literal = literal
        status, data = conn.uid("SEARCH", *criteria)
        return data[0].split() if status == "OK" and data and data[0] else []

    def account(self):
        with self._mailbox():
            return self.settings.gmail_address

    def search(self, query, limit):
        """Headers only, newest first. No body is fetched until a message is imported."""
        with self._mailbox() as conn:
            uids = (self._uids(conn, "CHARSET", "UTF-8", "X-GM-RAW", literal=query.encode()) if query.strip()
                    else self._uids(conn, "ALL"))
            newest = uids[-limit:][::-1]
            if not newest:
                return []
            status, data = conn.uid("FETCH", b",".join(newest).decode(), META)
            by_uid = {}
            for meta, literal in _records(data) if status == "OK" else []:
                uid = re.search(rb"UID (\d+)", meta)
                headers = message_from_bytes(literal, policy=policy.default)
                message_id, thread_id = _ids(meta)
                by_uid[uid.group(1) if uid else b""] = {"message_id": message_id, "thread_id": thread_id,
                    "subject": str(headers.get("Subject", "")), "sender": str(headers.get("From", "")),
                    "date": str(headers.get("Date", "")), "snippet": ""}
            return [by_uid[u] for u in newest if u in by_uid and by_uid[u]["message_id"]]

    def _fetch(self, key, value):
        if not value.isdigit():  # Gmail IMAP IDs are decimal; anything else cannot match and must not reach IMAP.
            raise Problem("not_found", "Gmail message or thread not found", 404)
        with self._mailbox() as conn:
            uids = self._uids(conn, key, value)[:MAX_THREAD]
            if not uids:
                raise Problem("not_found", "Gmail message or thread not found", 404)
            status, data = conn.uid("FETCH", b",".join(uids).decode(), FULL)
            mails = [parse_rfc822(literal, *_ids(meta)) for meta, literal in _records(data)] if status == "OK" else []
        if not mails:
            raise Problem("gmail_error", "Gmail returned no message content", 502)
        return mails

    def message(self, message_id):
        return self._fetch("X-GM-MSGID", message_id)[0]

    def thread(self, thread_id):
        return self._fetch("X-GM-THRID", thread_id)

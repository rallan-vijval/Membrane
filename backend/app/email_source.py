"""Turn Gmail API messages into the plain text and preview image a Membrane source needs.

Nothing is summarized or altered here: headers and the text body are laid out as written, and
anything cut for length says so. Email content is untrusted data like any other source.
"""
import base64
import re
import textwrap
from html.parser import HTMLParser
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

MAX_PREVIEW_LINES = 110
TRUNCATED = "\n[Truncated: the rest of this email is not included.]"


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table", "blockquote"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _walk(part):
    yield part
    for child in part.get("parts", []) or []:
        yield from _walk(child)


def _clean(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse(message):
    """One Gmail `format=full` message -> headers, text body and attachment names."""
    payload = message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    plain, html, attachments = [], [], []
    for part in _walk(payload):
        body = part.get("body", {})
        if part.get("filename"):
            attachments.append(part["filename"])
        elif body.get("data") and part.get("mimeType") == "text/plain":
            plain.append(_decode(body["data"]))
        elif body.get("data") and part.get("mimeType") == "text/html":
            html.append(_decode(body["data"]))
    if plain:
        text = "\n".join(plain)
    else:
        parser = _Text()
        parser.feed("\n".join(html))
        text = "".join(parser.parts)
    return {"message_id": message["id"], "thread_id": message.get("threadId", ""),
            "subject": headers.get("subject", ""), "sender": headers.get("from", ""),
            "date": headers.get("date", ""), "body": _clean(text), "attachments": attachments}


def render_text(emails, limit):
    """The exact text given to extraction and shown to the reviewer. Attachments are named, not read."""
    blocks = []
    for mail in emails:
        lines = [f"Subject: {mail['subject']}", f"From: {mail['sender']}", f"Date: {mail['date']}"]
        if mail["attachments"]:
            lines.append("Attachments (not read): " + ", ".join(mail["attachments"]))
        blocks.append("\n".join(lines) + "\n\n" + mail["body"])
    text = "\n\n----- next message in thread -----\n\n".join(blocks)
    return text if len(text) <= limit else text[:limit - len(TRUNCATED)] + TRUNCATED


def render_png(text):
    """Typeset the email text as the preview image the review UI shows for every source."""
    font = ImageFont.load_default(size=16)
    lines = []
    for raw in text.split("\n"):
        lines.extend(textwrap.wrap(raw, 100, replace_whitespace=False, drop_whitespace=False) or [""])
    shown = lines[:MAX_PREVIEW_LINES]
    if len(lines) > MAX_PREVIEW_LINES:
        shown.append(f"[Preview shows the first {MAX_PREVIEW_LINES} lines.]")
    pad, height = 40, 22
    image = Image.new("RGB", (1000, pad * 2 + height * len(shown)), "#ffffff")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(shown):
        draw.text((pad, pad + i * height), line, fill="#111827", font=font)
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()

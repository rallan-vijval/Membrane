# Gmail as a source

Membrane can take an email (or a whole thread) from Gmail as a source. It is treated exactly like an
uploaded screenshot: untrusted, staged as a candidate, tested against the paired suite, and only
activated after review. Membrane does not sync a mailbox, and cannot send, delete or modify mail.

## What it reads

- **Search** returns subject, sender, date and Gmail's snippet only. Nothing is stored.
- **Import** reads the one email or thread you picked. Headers and the text body are kept word for
  word (HTML-only mail is reduced to its text). Attachments are named in the source but never read.
- The Gmail account, message IDs and thread ID are recorded in the source's `provenance`.
- Long mail is cut at `GMAIL_MAX_EMAIL_CHARS` (default 12000) with a visible marker.

## One-time setup (about five minutes)

1. In Google Cloud Console, enable the **Gmail API** and create an OAuth client of type
   **Desktop app**. Add your Gmail address as a test user on the consent screen.
2. Put the client in `.env` (never commit it):
   ```
   GMAIL_CLIENT_ID=...
   GMAIL_CLIENT_SECRET=...
   ```
3. Run `python -m scripts.gmail_authorize` and approve the read-only request in the browser.
   The script writes `GMAIL_REFRESH_TOKEN` and `GMAIL_ENABLED=true` to `.env`; it never prints the token.
4. Restart the backend. In the app open **Or pick an email from Gmail**; it shows the connected address.

The only scope requested is `https://www.googleapis.com/auth/gmail.readonly`.

## API

| Route | Purpose |
| --- | --- |
| `GET /api/gmail/status` | Live check of the grant; returns the connected address, never credentials |
| `GET /api/gmail/messages?q=&limit=` | Search metadata (Gmail search syntax), up to 25 |
| `POST /api/gmail/messages/{id}/import` | Import one email as a `Source` |
| `POST /api/gmail/threads/{id}/import` | Import a thread (first 20 messages) as one `Source` |

Extraction uses the text model (`AGENT_MODEL`), not vision: the email text itself is the source's
`extracted_text`, and the model only proposes the memory, its scope and a supporting quote. A quote
that is not an exact substring of the email is dropped.

## Verification status

Unit and browser tests replace Google with an in-test transport. A live Gmail request has not been
run yet; it needs the OAuth client above.

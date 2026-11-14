# Gmail as a source

Membrane can take an email (or a whole thread) from Gmail as a source. It is treated exactly like an
uploaded screenshot: untrusted, staged as a candidate, tested against the paired suite, and only
activated after review. Membrane does not sync a mailbox and never sends, deletes or modifies mail.

## What it reads

- **Search** returns subject, sender, date and Gmail's snippet only. Nothing is stored.
- **Import** reads the one email or thread you picked. Headers and the text body are kept word for
  word (HTML-only mail is reduced to its text). Attachments are named in the source but never read.
- The Gmail account, message IDs and thread ID are recorded in the source's `provenance`.
- Long mail is cut at `GMAIL_MAX_EMAIL_CHARS` (default 12000) with a visible marker.

## Setup A: app password (no Google Cloud project)

1. Turn on 2-Step Verification for the Gmail account, then create an app password in the Google
   Account security settings (search for "App passwords"). Work/school and Advanced Protection
   accounts may not allow this.
2. Put these in `.env` (never commit them, never paste them in chat):
   ```
   GMAIL_ENABLED=true
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```
3. Restart the backend. In the app open **Or pick an email from Gmail**; it shows the connected address.

An app password is **not** read-only at Google's side: it can do anything IMAP can. Membrane limits
itself in code: the mailbox is opened read-only, bodies are fetched with `BODY.PEEK` (mail is not
marked as read), and nothing is written, moved or deleted. For a demo, a separate Gmail account
with synthetic emails is the safest choice. Revoke the app password in the same settings page when done.
Search results have no preview snippet in this mode.

## Setup B: OAuth read-only grant (needs Google Cloud Console)

Used when no app password is set. Google itself enforces read-only
(`https://www.googleapis.com/auth/gmail.readonly`).

1. In Google Cloud Console, enable the **Gmail API** and create an OAuth client of type
   **Desktop app**. Add your Gmail address as a test user on the consent screen.
2. Put `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` in `.env`.
3. Run `python -m scripts.gmail_authorize` and approve the request in the browser. The script writes
   `GMAIL_REFRESH_TOKEN` and `GMAIL_ENABLED=true` to `.env`; it never prints the token.
4. Restart the backend.

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

Unit and browser tests replace Google (HTTP and IMAP) with in-test stand-ins. A live Gmail request has not been
run yet; it needs credentials from Setup A or B.

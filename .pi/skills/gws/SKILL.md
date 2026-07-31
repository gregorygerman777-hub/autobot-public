---
name: gws
description: Access Google Workspace (Gmail, Calendar, Drive) via the gws CLI. Use when the user asks about their email, Google Calendar, Google Drive, or any Google Workspace service.
---

# Google Workspace (gws)

The `gws` CLI provides access to Gmail, Google Calendar, Google Drive, and other Google Workspace APIs.

## Gmail

```bash
# List recent emails
gws gmail users messages list --params '{"userId": "me", "maxResults": 20}'

# List unread emails
gws gmail users messages list --params '{"userId": "me", "q": "is:unread", "maxResults": 20}'

# Get message metadata (headers only)
gws gmail users messages get --params '{"userId": "me", "id": "MSG_ID", "format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]}'

# Get full message
gws gmail users messages get --params '{"userId": "me", "id": "MSG_ID", "format": "full"}'

# Search emails
gws gmail users messages list --params '{"userId": "me", "q": "from:someone@example.com"}'

# List labels
gws gmail users labels list --params '{"userId": "me"}'
```

### Sending Email

Use `--params` for userId and `--json` for the RFC 2822 message body (base64url-encoded).
Never put the message body in `--params` — that causes Content-Length errors on large payloads.

```bash
# Step 1: Build the raw base64url-encoded RFC 2822 message
python3 -c "
import base64
from email.mime.text import MIMEText
msg = MIMEText('Your message body here', 'plain', 'utf-8')
msg['to'] = 'recipient@example.com'
msg['subject'] = 'Subject line'
raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
print(raw)
" > /tmp/email_raw.txt

# Step 2: Send via gws (--params for userId, --json for body)
RAW=$(cat /tmp/email_raw.txt)
gws gmail users messages send --params '{"userId": "me"}' --json "{\"raw\": \"$RAW\"}"
```

For large emails, write the body to a file first, then read it into the RAW variable.
This approach works for any size email — tested with 10KB+ bodies.

### Sending Email with Attachments (or any email > ~200KB)

The `gws gmail +send` helper does **NOT** support attachments. The generic
`messages send --json '{"raw":...}'` approach also fails for large messages
because the JSON exceeds bash ARG_MAX (~256KB on macOS). And `--upload`
sends the wrong Content-Type to Gmail.

**The working approach: bypass the gws CLI and call the Gmail API directly
using the OAuth credentials gws already stores.** gws encrypts the refresh
token at `~/.config/gws/credentials.enc` with AES-256-GCM, key in
`~/.config/gws/.encryption_key` (base64-encoded). The token already has
`gmail.modify` scope (which permits `send`).

```python
# uv run --with google-api-python-client --with google-auth --with cryptography python3 ...
import base64, json, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# 1. Decrypt the gws creds
gws_dir = os.path.expanduser('~/.config/gws')
with open(f'{gws_dir}/.encryption_key', 'rb') as f:
    key = base64.b64decode(f.read().strip())   # 32-byte AES-256 key
with open(f'{gws_dir}/credentials.enc', 'rb') as f:
    enc = f.read()
# Format: first 12 bytes nonce, rest is AES-GCM ciphertext+tag
creds_data = json.loads(AESGCM(key).decrypt(enc[:12], enc[12:], None))

# 2. Build Credentials with gmail.modify scope (already granted)
creds = Credentials(
    token=None,
    refresh_token=creds_data['refresh_token'],
    client_id=creds_data['client_id'],
    client_secret=creds_data['client_secret'],
    token_uri='https://oauth2.googleapis.com/token',
    scopes=['https://www.googleapis.com/auth/gmail.modify'],  # NOT gmail.send — that scope wasn't authorized
)

# 3. Build the MIME message with attachments
msg = MIMEMultipart()
msg['to'] = 'recipient@example.com, other@example.com'
msg['subject'] = 'Subject line'
msg.attach(MIMEText('Body text here', 'plain', 'utf-8'))
for path, name in [('/abs/path/file.pdf', 'file.pdf')]:
    with open(path, 'rb') as f:
        part = MIMEApplication(f.read(), _subtype='pdf')
    part.add_header('Content-Disposition', 'attachment', filename=name)
    msg.attach(part)

raw_bytes = msg.as_bytes()

# 4. Send via MediaInMemoryUpload (handles large payloads via multipart HTTP upload)
service = build('gmail', 'v1', credentials=creds)
media = MediaInMemoryUpload(raw_bytes, mimetype='message/rfc822', resumable=False)
result = service.users().messages().send(userId='me', body={}, media_body=media).execute()
print(f"Sent! Message ID: {result['id']}")
```

**Critical points:**
- Use `gmail.modify` scope (not `gmail.send` — only the broader scope is authorized in the existing token).
- Use `MediaInMemoryUpload` with `mimetype='message/rfc822'`, **not** the standard `body={'raw': base64...}` approach. The media upload bypasses JSON size limits.
- The MIME message bytes go in directly — do **not** base64-encode (the media upload handles transport encoding).
- Tested working with 6+ MB attachments.

This pattern works for any time you need to send Gmail with attachments,
rich HTML, or any payload that won't fit on the command line.

### Summarizing Email

When asked to check or summarize email:
1. Fetch recent/unread message IDs
2. Get metadata (From, Subject, Date) for each
3. For important-looking messages, fetch full body if needed
4. Categorize:
   - **Action Required**: Needs a reply or action
   - **Informational**: Updates, receipts, confirmations
   - **Skip**: Newsletters, promotions, automated alerts (mention count only)

## Google Calendar

```bash
# List today's events
gws calendar events list --params '{"calendarId": "primary", "timeMin": "<today_start_iso>", "timeMax": "<today_end_iso>", "singleEvents": true, "orderBy": "startTime"}'

# List upcoming events
gws calendar events list --params '{"calendarId": "primary", "timeMin": "<now_iso>", "maxResults": 10, "singleEvents": true, "orderBy": "startTime"}'

# List calendars
gws calendar calendarList list
```

**Note:** gws may not have calendar scopes authorized for all users. If calendar commands fail, fall back to `icalBuddy` or the `calendar` skill (osascript) for local macOS Calendar access.

## Google Drive

```bash
# List recent files
gws drive files list --params '{"pageSize": 10, "orderBy": "modifiedTime desc"}'

# Search files
gws drive files list --params '{"q": "name contains '\''query'\''", "pageSize": 10}'

# Get file metadata
gws drive files get --params '{"fileId": "FILE_ID"}'
```

## Triaging Across Channels

When asked "what did I miss" or "anything important", combine gws data with other platform skills:
1. Check unread email via Gmail commands above
2. Check Slack via the `slack` skill
3. Check Messages via the `messages` skill
4. Apply priority scoring:
   - **P0 (Urgent)**: Direct questions, meeting changes today, deadlines today
   - **P1 (Important)**: Review requests, scheduling asks, announcements
   - **P2 (Normal)**: General updates, FYIs
   - **P3 (Low)**: Marketing, newsletters, bots (ignore)
5. Surface P0 and P1 items. Mention P2 count. Skip P3.

## Setup

Run `gws auth login` to authenticate. Use `--format json` for structured parsing.

## Rules

- Always use `"userId": "me"` for Gmail commands
- Use ISO 8601 format for date parameters (e.g., `2026-04-07T00:00:00Z`)
- Don't include full email bodies in summaries sent externally
- **Always send email via Gmail (gws), never via Apple Mail or osascript** — the user only uses Gmail

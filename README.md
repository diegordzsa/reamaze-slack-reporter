# Reamaze Slack Reporter

Daily 9am Madrid report of Re:amaze replies sent the prior day, posted to Slack.

Counts staff replies (visibility = regular, with at least one prior customer message in the thread) and computes average response time.

## Setup

### 1. Local environment

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Get credentials

- **Re:amaze API token**: Re:amaze dashboard → your avatar → Settings → look for "API Token" (each user has their own; use an admin account so it can read all conversations and the staff list).
- **Brand subdomain**: the `xxx` in `xxx.reamaze.io` or `xxx.reamaze.com`.
- **Slack webhook**: create an Incoming Webhook in the target Slack workspace and copy the URL.

### 3. Test locally

```powershell
$env:REAMAZE_BRAND="yourbrand"
$env:REAMAZE_LOGIN_EMAIL="you@example.com"
$env:REAMAZE_API_TOKEN="..."
$env:SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
python test_report_preview.py
```

The dry-run hits the real API but does NOT post to Slack. Verify the reply count matches a day where you know the answer before trusting the automation.

### 4. Deploy

Push to GitHub. Add 4 secrets in repo Settings → Secrets and variables → Actions:

- `REAMAZE_BRAND`
- `REAMAZE_LOGIN_EMAIL`
- `REAMAZE_API_TOKEN`
- `SLACK_WEBHOOK_URL`

Trigger manually once via Actions tab → "Daily Reamaze Report" → "Run workflow" to confirm it works before waiting for the scheduled run.

## Schedule

`0 7 * * *` UTC = 9am Madrid in summer (CEST), 8am Madrid in winter (CET). Accepted 1h winter drift.

## Notes on what counts as a "reply"

A message counts as a reply if all of these are true:

1. Sender's email is in the brand's staff list (so customer messages are excluded).
2. `visibility == 0` (regular message, not an internal note or collision).
3. At least one customer message exists earlier in the same conversation thread (excludes outbound conversations the staff started).

Response time = time between this reply and the most recent customer message that came before it in the same thread.

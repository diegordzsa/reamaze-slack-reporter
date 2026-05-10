import os

REAMAZE_BRAND = os.environ["REAMAZE_BRAND"]              # e.g. "yourbrand" (the subdomain)
REAMAZE_LOGIN_EMAIL = os.environ["REAMAZE_LOGIN_EMAIL"]  # your login email
REAMAZE_API_TOKEN = os.environ["REAMAZE_API_TOKEN"]      # individual API token
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]
REPORT_TIMEZONE = "Europe/Madrid"

# Channel/inbox emails used by staff to reply (also receives automated notifications)
CHANNEL_INBOX_EMAILS = {
    "contacto@hairbiolabs.com",
}

# Automated notification senders to exclude from customer counts
NOTIFICATION_SENDERS = {
    "no-reply@merchanto.org",
    "no-reply@klaviyo.com",
    "noreply@klaviyo.com",
    "support@appstle.com",
    "np@neilpatel.com",
    "mailer@shopify.com",
    "noreply@shopify.com",
    "hello@disputifier.com",
}

NOTIFICATION_DOMAINS = {
    "klaviyo.com",
    "shopify.com",
    "merchanto.org",
    "disputifier.com",
}
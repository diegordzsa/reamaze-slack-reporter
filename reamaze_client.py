import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pytz
import requests
from dateutil import parser as date_parser

from config import REAMAZE_BRAND, REAMAZE_LOGIN_EMAIL, REAMAZE_API_TOKEN

BASE_URL = f"https://{REAMAZE_BRAND}.reamaze.io/api/v1"
AUTH = (REAMAZE_LOGIN_EMAIL, REAMAZE_API_TOKEN)
HEADERS = {"Accept": "application/json"}


@dataclass
class ReplyStats:
    reply_count: int
    received_count: int
    still_waiting: int
    avg_response_time_minutes: Optional[float]
    replies_with_response_time: int


def _get(path: str, params: dict = None, retries: int = 3) -> dict:
    """GET with basic auth + simple 429 backoff."""
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        r = requests.get(url, auth=AUTH, headers=HEADERS, params=params or {}, timeout=30)
        if r.status_code == 429:
            wait = 2 ** attempt
            print(f"Rate limited, sleeping {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Failed after {retries} retries: {url}")


def _fetch_messages_in_window(start: datetime, end: datetime) -> list[dict]:
    """Fetch all messages in window. Paginates through results."""
    messages = []
    page = 1
    while True:
        data = _get(
            "/messages",
            params={
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "page": page,
            },
        )
        batch = data.get("messages", [])
        if not batch:
            break
        messages.extend(batch)
        if len(batch) < 30:
            break
        page += 1
        if page > 50:  # hard safety
            print("Hit page cap of 50, stopping pagination")
            break
    return messages


def _fetch_conversation_messages(slug: str) -> list[dict]:
    """Get all messages in a single conversation, sorted by created_at ascending."""
    data = _get(f"/conversations/{slug}/messages")
    msgs = data.get("messages", [])
    msgs.sort(key=lambda m: date_parser.isoparse(m["created_at"]))
    return msgs


def _fetch_staff_emails() -> set:
    """Return lowercase set of all staff emails for the brand."""
    emails = set()
    page = 1
    while True:
        data = _get("/staff", params={"page": page})
        batch = data.get("staff", [])
        if not batch:
            break
        for s in batch:
            if s.get("email"):
                emails.add(s["email"].lower())
        if len(batch) < 30:
            break
        page += 1
        if page > 20:
            break
    print(f"Loaded {len(emails)} staff emails")
    return emails


def _msg_sender_email(msg: dict) -> str:
    user = msg.get("user") or {}
    return (user.get("email") or "").lower()


def _conversation_slug(msg: dict) -> Optional[str]:
    conv = msg.get("conversation") or {}
    return conv.get("slug")


def collect_reply_stats(target_date_local: datetime, tz) -> ReplyStats:
    """
    target_date_local: midnight (local) of the day to report on.
    tz: pytz timezone for local day boundaries.
    """
    day_start_local = tz.localize(datetime(target_date_local.year,
                                           target_date_local.month,
                                           target_date_local.day))
    day_end_local = day_start_local + timedelta(days=1)
    start_dt = day_start_local.astimezone(pytz.UTC)
    end_dt = day_end_local.astimezone(pytz.UTC)

    # Pull all staff identities so we can identify staff messages reliably
    staff_emails = _fetch_staff_emails()

    # Fetch candidate messages (all messages in window)
    candidates = _fetch_messages_in_window(start_dt, end_dt)
    print(f"Pulled {len(candidates)} messages in window")

    # Filter to staff messages only (visibility 0 = regular, not internal note)
    staff_msgs = [
        m for m in candidates
        if _msg_sender_email(m) in staff_emails and m.get("visibility") == 0
    ]
    print(f"  -> {len(staff_msgs)} are staff regular messages")

    # Count inbound customer messages (visibility 0, sender NOT in staff)
    received_count = sum(
        1 for m in candidates
        if m.get("visibility") == 0
        and _msg_sender_email(m) not in staff_emails
        and _msg_sender_email(m)  # exclude messages with no sender email
    )
    print(f"  -> {received_count} inbound customer messages")

    # Build set of conversation slugs that had customer activity yesterday
    customer_msg_slugs = {
        _conversation_slug(m) for m in candidates
        if m.get("visibility") == 0
        and _msg_sender_email(m) not in staff_emails
        and _msg_sender_email(m)
        and _conversation_slug(m)
    }
    print(f"  -> across {len(customer_msg_slugs)} unique conversations")

    # For each candidate, load its conversation and check it's a reply
    reply_count = 0
    response_times = []  # in seconds
    conversation_cache = {}

    for m in staff_msgs:
        slug = _conversation_slug(m)
        if not slug:
            continue
        if slug not in conversation_cache:
            conversation_cache[slug] = _fetch_conversation_messages(slug)
        thread = conversation_cache[slug]

        # Find most recent customer message strictly before this one
        msg_time = date_parser.isoparse(m["created_at"])
        prior_customer = None
        for prior in thread:
            prior_time = date_parser.isoparse(prior["created_at"])
            if prior_time >= msg_time:
                break
            if (prior.get("visibility") == 0
                    and _msg_sender_email(prior) not in staff_emails):
                prior_customer = prior

        if prior_customer is None:
            # Staff started the thread — this is an outbound, skip
            continue

        reply_count += 1
        delta = msg_time - date_parser.isoparse(prior_customer["created_at"])
        response_times.append(delta.total_seconds())

    if response_times:
        avg_minutes = (sum(response_times) / len(response_times)) / 60.0
    else:
        avg_minutes = None

    # Count conversations still awaiting a reply: latest message in thread is from customer.
    # Fetch any conversation we haven't already loaded.
    still_waiting = 0
    for slug in customer_msg_slugs:
        if slug not in conversation_cache:
            conversation_cache[slug] = _fetch_conversation_messages(slug)
        thread = conversation_cache[slug]
        if not thread:
            continue
        # Last regular message (ignore internal notes)
        regular_msgs = [m for m in thread if m.get("visibility") == 0]
        if not regular_msgs:
            continue
        last = regular_msgs[-1]
        if _msg_sender_email(last) not in staff_emails and _msg_sender_email(last):
            still_waiting += 1
    print(f"  -> {still_waiting} conversations still waiting for a reply")

    return ReplyStats(
        reply_count=reply_count,
        received_count=received_count,
        still_waiting=still_waiting,
        avg_response_time_minutes=avg_minutes,
        replies_with_response_time=len(response_times),
    )

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pytz
import requests
from dateutil import parser as date_parser

from config import (
    REAMAZE_BRAND, REAMAZE_LOGIN_EMAIL, REAMAZE_API_TOKEN,
    CHANNEL_INBOX_EMAILS, NOTIFICATION_SENDERS, NOTIFICATION_DOMAINS,
)

BASE_URL = f"https://{REAMAZE_BRAND}.reamaze.io/api/v1"
AUTH = (REAMAZE_LOGIN_EMAIL, REAMAZE_API_TOKEN)
HEADERS = {"Accept": "application/json"}


@dataclass
class ReplyStats:
    reply_count: int
    received_count: int
    new_conversations: int
    conversations_touched: int
    still_waiting: int
    avg_response_time_minutes: Optional[float]
    replies_with_response_time: int
    notification_count: int


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


def _paginate(path: str, key: str, params: dict = None, max_pages: int = 100) -> list[dict]:
    """Generic paginator that uses the API's page_count field."""
    items = []
    base_params = dict(params or {})
    page = 1
    while True:
        base_params["page"] = page
        data = _get(path, params=base_params)
        batch = data.get(key, [])
        if not batch:
            break
        items.extend(batch)
        page_count = data.get("page_count", 1)
        if page >= page_count:
            break
        page += 1
        if page > max_pages:
            print(f"Hit page cap of {max_pages}, stopping pagination")
            break
    return items


def _fetch_messages_in_window(start: datetime, end: datetime) -> list[dict]:
    return _paginate("/messages", "messages", params={
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    })


def _fetch_conversation_messages(slug: str) -> list[dict]:
    msgs = _paginate(f"/conversations/{slug}/messages", "messages", max_pages=50)
    msgs.sort(key=lambda m: date_parser.isoparse(m["created_at"]))
    return msgs


def _fetch_staff_info() -> tuple[set, set]:
    """Return (lowercase emails, lowercase names) for all staff."""
    emails = set()
    names = set()
    staff_list = _paginate("/staff", "staff", max_pages=20)
    for s in staff_list:
        if s.get("email"):
            emails.add(s["email"].lower())
        if s.get("name"):
            names.add(s["name"].lower())
    emails.update(e.lower() for e in CHANNEL_INBOX_EMAILS)
    print(f"Loaded {len(emails)} staff emails, {len(names)} staff names")
    return emails, names


def _msg_sender_email(msg: dict) -> str:
    user = msg.get("user") or {}
    return (user.get("email") or "").lower()


def _msg_sender_name(msg: dict) -> str:
    user = msg.get("user") or {}
    return (user.get("name") or "").lower()


def _conversation_slug(msg: dict) -> Optional[str]:
    conv = msg.get("conversation") or {}
    return conv.get("slug")


def _is_notification_sender(email: str) -> bool:
    if not email:
        return False
    email = email.lower()
    if email in NOTIFICATION_SENDERS:
        return True
    domain = email.split("@", 1)[-1] if "@" in email else ""
    return domain in NOTIFICATION_DOMAINS


_channel_inbox_lower = {e.lower() for e in CHANNEL_INBOX_EMAILS}


def _classify_message(msg: dict, staff_emails: set, staff_names: set) -> str:
    """Classify a message as 'staff', 'customer', 'notification', or 'skip'."""
    if msg.get("visibility") != 0:
        return "skip"

    email = _msg_sender_email(msg)
    if not email:
        return "skip"

    # Personal staff email (not a channel inbox)
    if email in staff_emails and email not in _channel_inbox_lower:
        return "staff"

    # Channel inbox: staff reply only if sender name matches a known staff member
    if email in _channel_inbox_lower:
        name = _msg_sender_name(msg)
        if name and name in staff_names:
            return "staff"
        return "notification"

    if _is_notification_sender(email):
        return "notification"

    return "customer"


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

    staff_emails, staff_names = _fetch_staff_info()

    candidates = _fetch_messages_in_window(start_dt, end_dt)
    print(f"Pulled {len(candidates)} messages in window")

    # Classify every message
    staff_msgs = []
    received_count = 0
    notification_count = 0
    staff_slugs = set()

    for m in candidates:
        label = _classify_message(m, staff_emails, staff_names)
        if label == "staff":
            staff_msgs.append(m)
            slug = _conversation_slug(m)
            if slug:
                staff_slugs.add(slug)
        elif label == "customer":
            received_count += 1
        elif label == "notification":
            notification_count += 1

    conversations_touched = len(staff_slugs)
    print(f"  -> {len(staff_msgs)} staff messages, {received_count} customer, "
          f"{notification_count} notifications filtered")
    print(f"  -> {conversations_touched} conversations touched")

    # Build set of slugs with real customer activity (for still-waiting check)
    customer_msg_slugs = {
        _conversation_slug(m) for m in candidates
        if _classify_message(m, staff_emails, staff_names) == "customer"
        and _conversation_slug(m)
    }

    # Reply detection: load threads for staff messages
    reply_count = 0
    response_times = []
    conversation_cache = {}

    for m in staff_msgs:
        slug = _conversation_slug(m)
        if not slug:
            continue
        if slug not in conversation_cache:
            conversation_cache[slug] = _fetch_conversation_messages(slug)
        thread = conversation_cache[slug]

        msg_time = date_parser.isoparse(m["created_at"])
        prior_customer = None
        for prior in thread:
            prior_time = date_parser.isoparse(prior["created_at"])
            if prior_time >= msg_time:
                break
            if (prior.get("visibility") == 0
                    and _classify_message(prior, staff_emails, staff_names) == "customer"):
                prior_customer = prior

        if prior_customer is None:
            continue

        reply_count += 1
        delta = msg_time - date_parser.isoparse(prior_customer["created_at"])
        response_times.append(delta.total_seconds())

    if response_times:
        avg_minutes = (sum(response_times) / len(response_times)) / 60.0
    else:
        avg_minutes = None

    # New conversations: check if the earliest message in the thread is within the window
    new_conversations = 0
    for slug in staff_slugs:
        if slug not in conversation_cache:
            conversation_cache[slug] = _fetch_conversation_messages(slug)
        thread = conversation_cache[slug]
        if not thread:
            continue
        first_msg_time = date_parser.isoparse(thread[0]["created_at"])
        if start_dt <= first_msg_time < end_dt:
            new_conversations += 1

    # Still waiting: last regular message in thread is from a customer
    still_waiting = 0
    for slug in customer_msg_slugs:
        if slug not in conversation_cache:
            conversation_cache[slug] = _fetch_conversation_messages(slug)
        thread = conversation_cache[slug]
        if not thread:
            continue
        regular_msgs = [m for m in thread if m.get("visibility") == 0]
        if not regular_msgs:
            continue
        last = regular_msgs[-1]
        if _classify_message(last, staff_emails, staff_names) == "customer":
            still_waiting += 1

    print(f"  -> {new_conversations} new conversations")
    print(f"  -> {still_waiting} conversations still waiting for a reply")

    return ReplyStats(
        reply_count=reply_count,
        received_count=received_count,
        new_conversations=new_conversations,
        conversations_touched=conversations_touched,
        still_waiting=still_waiting,
        avg_response_time_minutes=avg_minutes,
        replies_with_response_time=len(response_times),
        notification_count=notification_count,
    )

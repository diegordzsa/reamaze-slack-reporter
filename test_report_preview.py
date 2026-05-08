"""Diagnostic dry-run: prints every filter step."""
from datetime import datetime, timedelta
from collections import Counter
import pytz
from dateutil import parser as date_parser
from config import REPORT_TIMEZONE
from reamaze_client import (
    _fetch_messages_in_window, _fetch_staff_emails,
    _msg_sender_email, _conversation_slug
)

def main():
    tz = pytz.timezone(REPORT_TIMEZONE)
    now_local = datetime.now(tz)
    yesterday = now_local - timedelta(days=1)
    target = datetime(yesterday.year, yesterday.month, yesterday.day)

    day_start = tz.localize(target)
    day_end = day_start + timedelta(days=1)
    start_utc = day_start.astimezone(pytz.UTC)
    end_utc = day_end.astimezone(pytz.UTC)

    print(f"\n=== DIAGNOSTIC: {target.date()} ===")
    print(f"UTC window: {start_utc} to {end_utc}\n")

    # Step 1: Staff emails
    staff = _fetch_staff_emails()
    print(f"[1] Staff emails loaded: {len(staff)}")
    for e in sorted(staff):
        print(f"    - {e}")

    # Step 2: Raw message pull
    msgs = _fetch_messages_in_window(start_utc, end_utc)
    print(f"\n[2] Total messages pulled in window: {len(msgs)}")

    # Step 3: Visibility breakdown
    vis_counts = Counter(m.get("visibility") for m in msgs)
    print(f"\n[3] Visibility breakdown: {dict(vis_counts)}")
    print("    (Re:amaze docs: 0 = regular, 1 = note, 2 = collision)")

    # Step 4: Sender email breakdown
    senders = Counter(_msg_sender_email(m) for m in msgs)
    print(f"\n[4] Top 20 senders:")
    for email, count in senders.most_common(20):
        is_staff = "✅ STAFF" if email in staff else "👤 customer"
        label = email if email else "(no email)"
        print(f"    {count:4d}  {label}  {is_staff}")

    # Step 5: Funnel
    regular = [m for m in msgs if m.get("visibility") == 0]
    print(f"\n[5] Regular messages (visibility=0): {len(regular)}")

    staff_regular = [m for m in regular if _msg_sender_email(m) in staff]
    print(f"[6] Staff regular messages: {len(staff_regular)}")

    customer_regular = [m for m in regular
                        if _msg_sender_email(m)
                        and _msg_sender_email(m) not in staff]
    print(f"[7] Customer regular messages: {len(customer_regular)}")

    # Step 6: Pagination check
    print(f"\n[8] Pagination check:")
    print(f"    If [2] is exactly 30 or a multiple of 30, pagination is likely OK.")
    print(f"    If [2] is exactly 25 or 50, the page-size assumption is wrong.")
    print(f"    Compare [2] to your dashboard's message count for this day.")

if __name__ == "__main__":
    main()

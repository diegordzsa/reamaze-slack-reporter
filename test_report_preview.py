"""Local dry-run: pulls real Re:amaze data, prints what would post to Slack."""
from datetime import datetime, timedelta

import pytz

from config import REPORT_TIMEZONE
from reamaze_client import collect_reply_stats
from slack_client import _format_response_time


def main():
    tz = pytz.timezone(REPORT_TIMEZONE)
    now_local = datetime.now(tz)
    yesterday_local = now_local - timedelta(days=1)
    target = datetime(yesterday_local.year, yesterday_local.month, yesterday_local.day)

    print(f"\n=== DRY RUN: {target.date()} ({REPORT_TIMEZONE}) ===\n")
    stats = collect_reply_stats(target, tz)

    print("\n--- Would post to Slack ---")
    print(f"Emails received:    {stats.received_count}")
    print(f"Replies sent:       {stats.reply_count}")
    print(f"Still waiting:      {stats.still_waiting}")
    print(f"Avg response time:  {_format_response_time(stats.avg_response_time_minutes)}")
    print(f"Timed replies:      {stats.replies_with_response_time}/{stats.reply_count}")


if __name__ == "__main__":
    main()

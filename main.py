from datetime import datetime, timedelta

import pytz

from config import REPORT_TIMEZONE
from reamaze_client import collect_reply_stats
from slack_client import send_report


def main():
    tz = pytz.timezone(REPORT_TIMEZONE)
    now_local = datetime.now(tz)
    yesterday_local = now_local - timedelta(days=1)
    target = datetime(yesterday_local.year, yesterday_local.month, yesterday_local.day)

    print(f"Reporting on {target.date()} ({REPORT_TIMEZONE})")
    stats = collect_reply_stats(target, tz)
    print(f"Result: {stats}")

    send_report(
        report_date=target,
        reply_count=stats.reply_count,
        avg_minutes=stats.avg_response_time_minutes,
        replies_timed=stats.replies_with_response_time,
    )
    print("Posted to Slack ✅")


if __name__ == "__main__":
    main()

import json
from datetime import datetime
from typing import Optional

import requests

from config import SLACK_WEBHOOK_URL


def _format_response_time(minutes: Optional[float]) -> str:
    if minutes is None:
        return "—"
    if minutes < 60:
        return f"{minutes:.1f} min"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} d"


def send_report(report_date: datetime, reply_count: int, received_count: int,
                new_conversations: int, conversations_touched: int,
                still_waiting: int, avg_minutes: Optional[float],
                replies_timed: int, notification_count: int = 0) -> None:
    date_str = report_date.strftime("%A, %b %d")
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Re:amaze Daily Report — {date_str}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Customer emails received:*\n{received_count}"},
                {"type": "mrkdwn", "text": f"*Staff replies sent:*\n{reply_count}"},
                {"type": "mrkdwn", "text": f"*New conversations:*\n{new_conversations}"},
                {"type": "mrkdwn", "text": f"*Conversations touched:*\n{conversations_touched}"},
                {"type": "mrkdwn", "text": f"*Still waiting:*\n{still_waiting}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Avg response time:*\n{_format_response_time(avg_minutes)}",
                },
            ],
        },
    ]
    context_parts = []
    if replies_timed != reply_count and reply_count > 0:
        context_parts.append(f"Response time based on {replies_timed}/{reply_count} replies")
    if notification_count > 0:
        context_parts.append(f"{notification_count} automated notifications excluded")
    if context_parts:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"_{' | '.join(context_parts)}_",
            }],
        })

    r = requests.post(
        SLACK_WEBHOOK_URL,
        data=json.dumps({"blocks": blocks}),
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    r.raise_for_status()

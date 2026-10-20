"""AWS Lambda entry point. Trigger with an EventBridge schedule (rate(15 minutes)).

Pass {"dry_run": true} in the event to test without posting.
"""
import logging

from publisher.main import run

logging.getLogger().setLevel(logging.INFO)  # Lambda pre-configures a handler


def handler(event, context):
    code = run(dry_run=bool((event or {}).get("dry_run")))
    return {"statusCode": 200 if code == 0 else 500, "exitCode": code}

"""
Slack Integration
=================

Handles all Slack-related functionality:
- Bolt app initialization
- Event handlers (messages, mentions)
- Message parsing and response formatting
"""

from src.slack.app import create_slack_app
from src.slack.handlers import register_handlers

__all__ = ["create_slack_app", "register_handlers"]

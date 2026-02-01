"""
Slack Bolt App
==============

Creates and configures the Slack Bolt application.

Slack Bolt is the official framework for building Slack apps. It provides:
- Socket Mode connection (no public URL needed)
- Event handling with decorators
- Built-in request verification
- Middleware support

Why Socket Mode?
- No need for a public URL or webhook
- Works behind firewalls
- Real-time bidirectional communication
- Great for development and small deployments

For production at scale, consider:
- HTTP mode with load balancing
- Event subscriptions with webhooks
"""

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from src.utils.config import get_config
from src.utils.logger import Logger

logger = Logger("SlackApp")


def create_slack_app() -> AsyncApp:
    """
    Create and configure the Slack Bolt app.

    Returns:
        Configured AsyncApp instance
    """
    config = get_config()

    # Create the Bolt app with our tokens
    app = AsyncApp(
        token=config.slack.bot_token,
        signing_secret=config.slack.signing_secret,
    )

    logger.info("Slack Bolt app created")

    return app


async def create_socket_handler(app: AsyncApp) -> AsyncSocketModeHandler:
    """
    Create a Socket Mode handler for the app.

    Socket Mode establishes a WebSocket connection to Slack,
    allowing the bot to receive events without a public URL.

    Args:
        app: The Bolt app instance

    Returns:
        Configured socket handler
    """
    config = get_config()

    handler = AsyncSocketModeHandler(
        app=app,
        app_token=config.slack.app_token
    )

    logger.info("Socket Mode handler created")

    return handler

"""
Slack Event Handlers
====================

Handles Slack events and routes them to the agent.

Event Types:
- app_mention: When someone mentions @MiniClawd in a channel
- message.im: Direct messages to the bot
- message.channels: Messages in channels (if subscribed)

Handler Pattern:
    1. Receive event from Slack
    2. Extract relevant information (user, channel, text)
    3. Send to agent for processing
    4. Reply with agent's response

Error Handling:
    - Acknowledge events quickly (within 3 seconds)
    - Process asynchronously for longer operations
    - Reply with error messages if things fail
"""

import re
from typing import TYPE_CHECKING

from slack_bolt.async_app import AsyncApp, AsyncAck, AsyncSay
from slack_sdk.web.async_client import AsyncWebClient

from src.utils.logger import Logger

if TYPE_CHECKING:
    from src.agent import Agent

logger = Logger("Handlers")

# Global agent reference (set during registration)
_agent: "Agent | None" = None


def register_handlers(app: AsyncApp, agent: "Agent") -> None:
    """
    Register all event handlers with the Slack app.

    Args:
        app: The Bolt app instance
        agent: The agent instance for processing requests
    """
    global _agent
    _agent = agent

    # Register handlers
    app.event("app_mention")(_handle_mention)
    app.event("message")(_handle_message)

    # Register a simple health check command
    app.command("/miniclawd")(_handle_command)

    logger.info("Registered Slack event handlers")


async def _handle_mention(
    event: dict,
    say: AsyncSay,
    client: AsyncWebClient
) -> None:
    """
    Handle @mentions of the bot in channels.

    When someone mentions @MiniClawd in a channel, we:
    1. Extract the message (removing the mention)
    2. Process with the agent
    3. Reply in the thread

    Args:
        event: The Slack event data
        say: Function to send messages
        client: Slack API client
    """
    if _agent is None:
        logger.error("Agent not initialized")
        await say("Sorry, I'm still starting up. Please try again in a moment.")
        return

    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text", "")
    thread_ts = event.get("thread_ts") or event.get("ts")

    # Remove the bot mention from the text
    # Mentions look like <@U123ABC>
    text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

    if not text:
        await say(
            text="Hi! How can I help you? Try asking me to summarize a channel or set a reminder.",
            thread_ts=thread_ts
        )
        return

    logger.info(f"Mention from {user_id} in {channel_id}: {text[:50]}...")

    try:
        # Process with the agent
        response = await _agent.process(
            user_id=user_id,
            message=text,
            channel_id=channel_id,
            channel_type="channel"
        )

        # Reply in the thread
        await say(text=response, thread_ts=thread_ts)

    except Exception as e:
        logger.error(f"Error handling mention", e)
        await say(
            text="Sorry, I encountered an error processing your request.",
            thread_ts=thread_ts
        )


async def _handle_message(
    event: dict,
    say: AsyncSay,
    client: AsyncWebClient,
    ack: AsyncAck
) -> None:
    """
    Handle direct messages to the bot.

    DM conversations have access to full memory context and
    personal information (unlike channel mentions).

    Args:
        event: The Slack event data
        say: Function to send messages
        client: Slack API client
        ack: Acknowledge function
    """
    # Only handle DMs (channel_type == "im")
    if event.get("channel_type") != "im":
        return

    # Ignore bot messages (including our own)
    if event.get("bot_id"):
        return

    # Ignore message subtypes (edits, deletes, etc.)
    if event.get("subtype"):
        return

    if _agent is None:
        logger.error("Agent not initialized")
        await say("Sorry, I'm still starting up. Please try again in a moment.")
        return

    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text", "")

    if not text:
        return

    logger.info(f"DM from {user_id}: {text[:50]}...")

    try:
        # Show typing indicator
        # Note: This requires the bot to have the appropriate scope
        try:
            await client.conversations_mark(channel=channel_id, ts=event.get("ts"))
        except Exception:
            pass  # Typing indicator is optional

        # Process with the agent (full context in DMs)
        response = await _agent.process(
            user_id=user_id,
            message=text,
            channel_id=channel_id,
            channel_type="dm"
        )

        # Reply
        await say(text=response)

    except Exception as e:
        logger.error(f"Error handling DM", e)
        await say(text="Sorry, I encountered an error processing your request.")


async def _handle_command(
    ack: AsyncAck,
    command: dict,
    say: AsyncSay
) -> None:
    """
    Handle the /miniclawd slash command.

    This provides a quick way to interact with the bot:
    - /miniclawd help - Show help
    - /miniclawd status - Show bot status
    - /miniclawd clear - Clear conversation history

    Args:
        ack: Acknowledge function (must be called within 3 seconds)
        command: The command data
        say: Function to send messages
    """
    # Acknowledge immediately
    await ack()

    if _agent is None:
        await say("Sorry, I'm still starting up.")
        return

    user_id = command.get("user_id")
    text = command.get("text", "").strip().lower()

    if text == "help" or not text:
        help_text = """*MiniClawd Bot* - Your Slack Assistant

*Commands:*
- `/miniclawd help` - Show this help message
- `/miniclawd status` - Check bot status
- `/miniclawd clear` - Clear your conversation history

*Features:*
- Mention me (@MiniClawd) in any channel to interact
- DM me for private conversations with full memory access
- Ask me to summarize channels, set reminders, create issues, and more!

*Examples:*
- "Summarize #engineering from the last 24 hours"
- "Remind me to send the report in 30 minutes"
- "Create a GitHub issue for the login bug"
- "Schedule a good morning message to #general at 9am daily"
"""
        await say(text=help_text)

    elif text == "status":
        # Get some stats
        from src.tools import tool_registry
        tool_count = len(tool_registry.list_names())

        status_text = f"""*Bot Status*
- Status: Online
- Tools available: {tool_count}
- Model: {_agent.model}

I'm ready to help!"""
        await say(text=status_text)

    elif text == "clear":
        _agent.clear_conversation(user_id)
        await say(text="Conversation history cleared! Starting fresh.")

    else:
        await say(text=f"Unknown command: `{text}`. Try `/miniclawd help`")

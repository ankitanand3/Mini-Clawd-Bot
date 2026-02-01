"""
Slack Tools
===========

Tools for interacting with Slack: fetching messages, posting, scheduling.

These tools allow the agent to:
- Retrieve and summarize channel messages
- Post messages to channels
- Schedule future messages
- Look up channel and user information

Slack API Notes:
- Uses the slack_sdk async client
- Rate limits apply (check headers in production)
- Bot must have appropriate scopes for each operation
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from src.tools import MCPTool, ToolResult, tool_registry
from src.utils.logger import Logger

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = Logger("SlackTools")

# Global reference to Slack client (set by main.py)
_slack_client: "AsyncWebClient | None" = None


def set_slack_client(client: "AsyncWebClient") -> None:
    """Set the Slack client for tools to use."""
    global _slack_client
    _slack_client = client


def _get_client() -> "AsyncWebClient":
    """Get the Slack client, raising if not set."""
    if _slack_client is None:
        raise RuntimeError("Slack client not initialized. Call set_slack_client() first.")
    return _slack_client


# ==============================================================================
# Tool: Fetch Messages
# ==============================================================================

async def _fetch_messages(params: dict) -> ToolResult:
    """
    Fetch messages from a Slack channel.

    This is used to get channel history for summarization or analysis.
    """
    client = _get_client()

    channel = params.get("channel")
    hours = params.get("hours", 24)
    limit = params.get("limit", 100)

    if not channel:
        return ToolResult(success=False, error="Channel is required")

    try:
        # Calculate the oldest timestamp
        oldest_time = datetime.now() - timedelta(hours=hours)
        oldest_ts = str(oldest_time.timestamp())

        # If channel starts with #, look it up by name
        if channel.startswith("#"):
            channel_name = channel[1:]
            channel_id = await _lookup_channel_id(channel_name)
            if not channel_id:
                return ToolResult(success=False, error=f"Channel {channel} not found")
        else:
            channel_id = channel

        # Fetch messages
        response = await client.conversations_history(
            channel=channel_id,
            oldest=oldest_ts,
            limit=limit
        )

        if not response["ok"]:
            return ToolResult(success=False, error=response.get("error", "Unknown error"))

        messages = response.get("messages", [])

        # Format messages for return
        formatted = []
        for msg in messages:
            if msg.get("subtype"):  # Skip system messages
                continue

            user_id = msg.get("user", "unknown")
            text = msg.get("text", "")
            ts = msg.get("ts", "")

            # Format timestamp
            try:
                ts_float = float(ts)
                time_str = datetime.fromtimestamp(ts_float).strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                time_str = ts

            formatted.append({
                "user": user_id,
                "text": text,
                "time": time_str
            })

        return ToolResult(success=True, data={
            "channel": channel,
            "message_count": len(formatted),
            "messages": formatted
        })

    except Exception as e:
        logger.error(f"Error fetching messages from {channel}", e)
        return ToolResult(success=False, error=str(e))


async def _lookup_channel_id(channel_name: str) -> str | None:
    """Look up a channel ID by name."""
    client = _get_client()

    try:
        response = await client.conversations_list(
            types="public_channel,private_channel",
            limit=200
        )

        for channel in response.get("channels", []):
            if channel["name"] == channel_name:
                return channel["id"]

        return None
    except Exception:
        return None


fetch_messages_tool = MCPTool(
    name="slack_fetch_messages",
    description="Fetch messages from a Slack channel within a time range. Use this to get context for summarization or to find specific discussions.",
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel ID or name (with # prefix like #general)"
            },
            "hours": {
                "type": "integer",
                "description": "Number of hours to look back (default: 24)",
                "default": 24
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to fetch (default: 100)",
                "default": 100
            }
        },
        "required": ["channel"]
    },
    execute=_fetch_messages
)


# ==============================================================================
# Tool: Post Message
# ==============================================================================

async def _post_message(params: dict) -> ToolResult:
    """Post a message to a Slack channel."""
    client = _get_client()

    channel = params.get("channel")
    text = params.get("text")
    thread_ts = params.get("thread_ts")

    if not channel or not text:
        return ToolResult(success=False, error="Channel and text are required")

    try:
        # Look up channel ID if name provided
        if channel.startswith("#"):
            channel_name = channel[1:]
            channel_id = await _lookup_channel_id(channel_name)
            if not channel_id:
                return ToolResult(success=False, error=f"Channel {channel} not found")
        else:
            channel_id = channel

        # Post the message
        kwargs = {
            "channel": channel_id,
            "text": text
        }
        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        response = await client.chat_postMessage(**kwargs)

        if not response["ok"]:
            return ToolResult(success=False, error=response.get("error", "Unknown error"))

        return ToolResult(success=True, data={
            "channel": channel,
            "message_ts": response.get("ts"),
            "posted": True
        })

    except Exception as e:
        logger.error(f"Error posting message to {channel}", e)
        return ToolResult(success=False, error=str(e))


post_message_tool = MCPTool(
    name="slack_post_message",
    description="Post a message to a Slack channel. Use this to send messages or replies.",
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel ID or name (with # prefix)"
            },
            "text": {
                "type": "string",
                "description": "The message text to post"
            },
            "thread_ts": {
                "type": "string",
                "description": "Thread timestamp to reply in (optional)"
            }
        },
        "required": ["channel", "text"]
    },
    execute=_post_message
)


# ==============================================================================
# Tool: Schedule Message
# ==============================================================================

async def _schedule_message(params: dict) -> ToolResult:
    """Schedule a message to be posted at a future time."""
    client = _get_client()

    channel = params.get("channel")
    text = params.get("text")
    post_at = params.get("post_at")  # Unix timestamp or ISO string

    if not channel or not text or not post_at:
        return ToolResult(success=False, error="Channel, text, and post_at are required")

    try:
        # Look up channel ID if name provided
        if channel.startswith("#"):
            channel_name = channel[1:]
            channel_id = await _lookup_channel_id(channel_name)
            if not channel_id:
                return ToolResult(success=False, error=f"Channel {channel} not found")
        else:
            channel_id = channel

        # Parse post_at if it's a string
        if isinstance(post_at, str):
            # Try to parse ISO format
            try:
                dt = datetime.fromisoformat(post_at.replace("Z", "+00:00"))
                post_at_ts = int(dt.timestamp())
            except ValueError:
                return ToolResult(success=False, error="Invalid post_at format")
        else:
            post_at_ts = int(post_at)

        # Schedule the message
        response = await client.chat_scheduleMessage(
            channel=channel_id,
            text=text,
            post_at=post_at_ts
        )

        if not response["ok"]:
            return ToolResult(success=False, error=response.get("error", "Unknown error"))

        return ToolResult(success=True, data={
            "channel": channel,
            "scheduled_message_id": response.get("scheduled_message_id"),
            "post_at": datetime.fromtimestamp(post_at_ts).isoformat()
        })

    except Exception as e:
        logger.error(f"Error scheduling message to {channel}", e)
        return ToolResult(success=False, error=str(e))


schedule_message_tool = MCPTool(
    name="slack_schedule_message",
    description="Schedule a message to be posted at a specific time in the future.",
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel ID or name (with # prefix)"
            },
            "text": {
                "type": "string",
                "description": "The message text to post"
            },
            "post_at": {
                "type": "string",
                "description": "When to post (ISO timestamp or Unix timestamp)"
            }
        },
        "required": ["channel", "text", "post_at"]
    },
    execute=_schedule_message
)


# ==============================================================================
# Tool: Get Channel Info
# ==============================================================================

async def _get_channel_info(params: dict) -> ToolResult:
    """Get information about a Slack channel."""
    client = _get_client()

    channel = params.get("channel")

    if not channel:
        return ToolResult(success=False, error="Channel is required")

    try:
        # Look up channel ID if name provided
        if channel.startswith("#"):
            channel_name = channel[1:]
            channel_id = await _lookup_channel_id(channel_name)
            if not channel_id:
                return ToolResult(success=False, error=f"Channel {channel} not found")
        else:
            channel_id = channel

        response = await client.conversations_info(channel=channel_id)

        if not response["ok"]:
            return ToolResult(success=False, error=response.get("error", "Unknown error"))

        channel_info = response.get("channel", {})

        return ToolResult(success=True, data={
            "id": channel_info.get("id"),
            "name": channel_info.get("name"),
            "topic": channel_info.get("topic", {}).get("value", ""),
            "purpose": channel_info.get("purpose", {}).get("value", ""),
            "member_count": channel_info.get("num_members", 0),
            "is_private": channel_info.get("is_private", False)
        })

    except Exception as e:
        logger.error(f"Error getting channel info for {channel}", e)
        return ToolResult(success=False, error=str(e))


get_channel_info_tool = MCPTool(
    name="slack_get_channel_info",
    description="Get information about a Slack channel including its topic, purpose, and member count.",
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel ID or name (with # prefix)"
            }
        },
        "required": ["channel"]
    },
    execute=_get_channel_info
)


# ==============================================================================
# Register all Slack tools
# ==============================================================================

def register_slack_tools():
    """Register all Slack tools with the registry."""
    tool_registry.register(fetch_messages_tool)
    tool_registry.register(post_message_tool)
    tool_registry.register(schedule_message_tool)
    tool_registry.register(get_channel_info_tool)
    logger.info("Registered Slack tools")


# Auto-register on import
register_slack_tools()

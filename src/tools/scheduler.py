"""
Scheduler Tools
===============

Tools for scheduling reminders and recurring tasks.

These tools allow the agent to:
- Set reminders for the user
- Schedule recurring messages
- Manage scheduled tasks

Scheduling is handled by APScheduler, which provides:
- One-time jobs (reminders)
- Cron-based recurring jobs
- Persistent job store (optional)

State Persistence:
    Scheduled tasks are saved to heartbeat_state.json so they survive
    bot restarts. On startup, pending tasks are re-scheduled.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Awaitable
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.tools import MCPTool, ToolResult, tool_registry
from src.utils.config import get_config
from src.utils.logger import Logger

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = Logger("Scheduler")


class TaskScheduler:
    """
    Manages scheduled tasks and reminders.

    The scheduler handles:
    - One-time reminders (e.g., "remind me in 30 minutes")
    - Recurring messages (e.g., "every morning at 9am")
    - Task state persistence across restarts

    Example:
        scheduler = TaskScheduler(slack_client, memory_dir)

        # Set a reminder
        await scheduler.set_reminder(
            user_id="U123",
            message="Send the report",
            when=datetime.now() + timedelta(minutes=30)
        )

        # Schedule a recurring message
        await scheduler.schedule_recurring(
            channel_id="C123",
            message="Good morning!",
            cron="0 9 * * *"  # Every day at 9am
        )
    """

    def __init__(
        self,
        slack_client: "AsyncWebClient",
        memory_dir: Path
    ):
        """
        Initialize the scheduler.

        Args:
            slack_client: Async Slack client for sending messages
            memory_dir: Directory for state persistence
        """
        self.slack_client = slack_client
        self.state_file = memory_dir / "heartbeat_state.json"
        self.scheduler = AsyncIOScheduler()

        # Track scheduled tasks
        self._tasks: dict[str, dict] = {}

        # Load persisted state
        self._load_state()

    def _load_state(self) -> None:
        """Load scheduled tasks from disk."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file) as f:
                state = json.load(f)

            self._tasks = state.get("tasks", {})

            # Re-schedule tasks that haven't fired yet
            now = datetime.now()
            for task_id, task in self._tasks.items():
                if task.get("type") == "reminder":
                    fire_time = datetime.fromisoformat(task["fire_time"])
                    if fire_time > now:
                        self._schedule_reminder_job(
                            task_id=task_id,
                            user_id=task["user_id"],
                            channel_id=task["channel_id"],
                            message=task["message"],
                            fire_time=fire_time
                        )
                elif task.get("type") == "recurring":
                    self._schedule_recurring_job(
                        task_id=task_id,
                        channel_id=task["channel_id"],
                        message=task["message"],
                        cron=task["cron"]
                    )

            logger.info(f"Loaded {len(self._tasks)} scheduled tasks")

        except Exception as e:
            logger.error(f"Error loading scheduler state", e)

    def _save_state(self) -> None:
        """Save scheduled tasks to disk."""
        try:
            state = {
                "tasks": self._tasks,
                "last_updated": datetime.now().isoformat()
            }

            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Error saving scheduler state", e)

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    async def set_reminder(
        self,
        user_id: str,
        channel_id: str,
        message: str,
        when: datetime
    ) -> str:
        """
        Set a one-time reminder.

        Args:
            user_id: User to remind
            channel_id: Channel/DM to send reminder in
            message: Reminder message
            when: When to fire the reminder

        Returns:
            Task ID for the reminder
        """
        task_id = f"reminder_{uuid.uuid4().hex[:8]}"

        # Store task info
        self._tasks[task_id] = {
            "type": "reminder",
            "user_id": user_id,
            "channel_id": channel_id,
            "message": message,
            "fire_time": when.isoformat(),
            "created": datetime.now().isoformat()
        }

        # Schedule the job
        self._schedule_reminder_job(task_id, user_id, channel_id, message, when)

        # Save state
        self._save_state()

        logger.info(f"Scheduled reminder {task_id} for {when}")
        return task_id

    def _schedule_reminder_job(
        self,
        task_id: str,
        user_id: str,
        channel_id: str,
        message: str,
        fire_time: datetime
    ) -> None:
        """Schedule the actual APScheduler job for a reminder."""

        async def send_reminder():
            try:
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    text=f"<@{user_id}> Reminder: {message}"
                )
                logger.info(f"Sent reminder {task_id}")

                # Remove from tasks after firing
                if task_id in self._tasks:
                    del self._tasks[task_id]
                    self._save_state()

            except Exception as e:
                logger.error(f"Error sending reminder {task_id}", e)

        self.scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(run_date=fire_time),
            id=task_id,
            replace_existing=True
        )

    async def schedule_recurring(
        self,
        channel_id: str,
        message: str,
        cron: str
    ) -> str:
        """
        Schedule a recurring message.

        Args:
            channel_id: Channel to post in
            message: Message to post
            cron: Cron expression (e.g., "0 9 * * *" for daily at 9am)

        Returns:
            Task ID for the recurring task
        """
        task_id = f"recurring_{uuid.uuid4().hex[:8]}"

        # Store task info
        self._tasks[task_id] = {
            "type": "recurring",
            "channel_id": channel_id,
            "message": message,
            "cron": cron,
            "created": datetime.now().isoformat()
        }

        # Schedule the job
        self._schedule_recurring_job(task_id, channel_id, message, cron)

        # Save state
        self._save_state()

        logger.info(f"Scheduled recurring task {task_id} with cron: {cron}")
        return task_id

    def _schedule_recurring_job(
        self,
        task_id: str,
        channel_id: str,
        message: str,
        cron: str
    ) -> None:
        """Schedule the actual APScheduler job for recurring messages."""

        async def post_message():
            try:
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    text=message
                )
                logger.debug(f"Posted recurring message {task_id}")

            except Exception as e:
                logger.error(f"Error posting recurring message {task_id}", e)

        # Parse cron expression
        parts = cron.split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week
            )
        else:
            # Default to daily at 9am if invalid
            trigger = CronTrigger(hour=9, minute=0)

        self.scheduler.add_job(
            post_message,
            trigger=trigger,
            id=task_id,
            replace_existing=True
        )

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a scheduled task.

        Args:
            task_id: The task ID to cancel

        Returns:
            True if the task was found and cancelled
        """
        if task_id not in self._tasks:
            return False

        try:
            self.scheduler.remove_job(task_id)
        except Exception:
            pass  # Job might have already fired

        del self._tasks[task_id]
        self._save_state()

        logger.info(f"Cancelled task {task_id}")
        return True

    def list_tasks(self) -> list[dict]:
        """Get all scheduled tasks."""
        return [
            {"id": k, **v}
            for k, v in self._tasks.items()
        ]


# Global scheduler instance (set by main.py)
_scheduler: TaskScheduler | None = None


def set_scheduler(scheduler: TaskScheduler) -> None:
    """Set the global scheduler instance."""
    global _scheduler
    _scheduler = scheduler


def get_scheduler() -> TaskScheduler:
    """Get the global scheduler instance."""
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialized")
    return _scheduler


# ==============================================================================
# Tool: Set Reminder
# ==============================================================================

async def _set_reminder(params: dict) -> ToolResult:
    """Set a reminder for the user."""
    scheduler = get_scheduler()

    user_id = params.get("user_id")
    channel_id = params.get("channel_id")
    message = params.get("message")
    minutes = params.get("minutes")

    if not user_id or not message:
        return ToolResult(success=False, error="User ID and message are required")

    if not minutes or minutes < 1:
        return ToolResult(success=False, error="Minutes must be at least 1")

    try:
        when = datetime.now() + timedelta(minutes=minutes)

        task_id = await scheduler.set_reminder(
            user_id=user_id,
            channel_id=channel_id or user_id,  # DM if no channel
            message=message,
            when=when
        )

        return ToolResult(success=True, data={
            "task_id": task_id,
            "message": message,
            "fire_time": when.isoformat(),
            "minutes": minutes
        })

    except Exception as e:
        logger.error(f"Error setting reminder", e)
        return ToolResult(success=False, error=str(e))


set_reminder_tool = MCPTool(
    name="set_reminder",
    description="Set a reminder that will ping the user after a specified number of minutes.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "Slack user ID to remind"
            },
            "channel_id": {
                "type": "string",
                "description": "Channel to post reminder in (defaults to DM)"
            },
            "message": {
                "type": "string",
                "description": "Reminder message"
            },
            "minutes": {
                "type": "integer",
                "description": "Minutes until reminder fires"
            }
        },
        "required": ["user_id", "message", "minutes"]
    },
    execute=_set_reminder
)


# ==============================================================================
# Tool: Schedule Recurring Message
# ==============================================================================

async def _schedule_recurring_message(params: dict) -> ToolResult:
    """Schedule a recurring message to a channel."""
    scheduler = get_scheduler()

    channel_id = params.get("channel_id")
    message = params.get("message")
    time = params.get("time", "09:00")  # HH:MM format
    days = params.get("days", "mon-fri")  # mon-sun or specific days

    if not channel_id or not message:
        return ToolResult(success=False, error="Channel ID and message are required")

    try:
        # Parse time
        hour, minute = time.split(":")
        hour = int(hour)
        minute = int(minute)

        # Parse days
        day_map = {
            "mon": "0", "tue": "1", "wed": "2", "thu": "3",
            "fri": "4", "sat": "5", "sun": "6",
            "mon-fri": "0-4", "weekdays": "0-4",
            "mon-sun": "*", "daily": "*", "everyday": "*"
        }

        day_of_week = day_map.get(days.lower(), days)

        # Build cron expression: minute hour day month day_of_week
        cron = f"{minute} {hour} * * {day_of_week}"

        task_id = await scheduler.schedule_recurring(
            channel_id=channel_id,
            message=message,
            cron=cron
        )

        return ToolResult(success=True, data={
            "task_id": task_id,
            "channel_id": channel_id,
            "message": message,
            "time": time,
            "days": days,
            "cron": cron
        })

    except Exception as e:
        logger.error(f"Error scheduling recurring message", e)
        return ToolResult(success=False, error=str(e))


schedule_recurring_tool = MCPTool(
    name="schedule_recurring_message",
    description="Schedule a recurring message to be posted to a channel at a specific time.",
    parameters={
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Channel ID to post in"
            },
            "message": {
                "type": "string",
                "description": "Message to post"
            },
            "time": {
                "type": "string",
                "description": "Time to post (HH:MM format, 24-hour)",
                "default": "09:00"
            },
            "days": {
                "type": "string",
                "description": "Days to post (mon-fri, daily, or comma-separated days)",
                "default": "mon-fri"
            }
        },
        "required": ["channel_id", "message"]
    },
    execute=_schedule_recurring_message
)


# ==============================================================================
# Tool: List Scheduled Tasks
# ==============================================================================

async def _list_scheduled_tasks(params: dict) -> ToolResult:
    """List all scheduled tasks."""
    scheduler = get_scheduler()

    tasks = scheduler.list_tasks()

    return ToolResult(success=True, data={
        "count": len(tasks),
        "tasks": tasks
    })


list_tasks_tool = MCPTool(
    name="list_scheduled_tasks",
    description="List all scheduled reminders and recurring messages.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    execute=_list_scheduled_tasks
)


# ==============================================================================
# Tool: Cancel Scheduled Task
# ==============================================================================

async def _cancel_task(params: dict) -> ToolResult:
    """Cancel a scheduled task."""
    scheduler = get_scheduler()

    task_id = params.get("task_id")

    if not task_id:
        return ToolResult(success=False, error="Task ID is required")

    success = scheduler.cancel_task(task_id)

    if success:
        return ToolResult(success=True, data={
            "task_id": task_id,
            "cancelled": True
        })
    else:
        return ToolResult(success=False, error=f"Task {task_id} not found")


cancel_task_tool = MCPTool(
    name="cancel_scheduled_task",
    description="Cancel a scheduled reminder or recurring message.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to cancel"
            }
        },
        "required": ["task_id"]
    },
    execute=_cancel_task
)


# ==============================================================================
# Register Scheduler tools
# ==============================================================================

def register_scheduler_tools():
    """Register all scheduler tools with the registry."""
    tool_registry.register(set_reminder_tool)
    tool_registry.register(schedule_recurring_tool)
    tool_registry.register(list_tasks_tool)
    tool_registry.register(cancel_task_tool)
    logger.info("Registered Scheduler tools")


# Auto-register on import
register_scheduler_tools()

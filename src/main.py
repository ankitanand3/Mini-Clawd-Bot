"""
MiniClawd Bot - Main Entry Point
=================================

This is the main entry point for the bot. It:
1. Loads configuration
2. Initializes all components (memory, RAG, tools, agent)
3. Sets up Slack handlers
4. Starts the bot

Run with:
    python -m src.main

Or after installing:
    miniclawd
"""

import asyncio
import signal
import sys

from src.utils.config import get_config
from src.utils.logger import logger, Logger

# Initialize logging early
main_logger = Logger("Main")


async def main():
    """
    Main async entry point.

    Initializes all components and runs the bot.
    """
    main_logger.info("Starting MiniClawd Bot...")

    try:
        # 1. Load configuration
        # This validates that all required env vars are set
        main_logger.info("Loading configuration...")
        config = get_config()

        # 2. Initialize memory system
        main_logger.info("Initializing memory system...")
        from src.memory import MemoryManager
        memory = MemoryManager()

        # 3. Create Slack app
        main_logger.info("Creating Slack app...")
        from src.slack.app import create_slack_app, create_socket_handler
        app = create_slack_app()

        # 4. Initialize RAG system
        main_logger.info("Initializing RAG system...")
        from src.rag import RAGManager
        rag = RAGManager(app.client)

        # 5. Set up tools
        main_logger.info("Setting up tools...")
        from src.tools.slack_tools import set_slack_client
        set_slack_client(app.client)

        # Set up scheduler
        from src.tools.scheduler import TaskScheduler, set_scheduler
        scheduler = TaskScheduler(app.client, config.memory.directory)
        set_scheduler(scheduler)
        scheduler.start()

        # 6. Create the agent
        main_logger.info("Creating agent...")
        from src.agent import Agent
        agent = Agent(memory=memory, rag=rag)

        # 7. Register event handlers
        main_logger.info("Registering event handlers...")
        from src.slack.handlers import register_handlers
        register_handlers(app, agent)

        # 8. Optionally index channels on startup
        if config.rag.messages_per_channel > 0:
            main_logger.info("Starting background channel indexing...")
            asyncio.create_task(_background_index(rag))

        # 9. Start the Socket Mode handler
        main_logger.info("Starting Socket Mode connection...")
        handler = await create_socket_handler(app)

        # Set up graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(_shutdown(handler, scheduler))
            )

        main_logger.info("MiniClawd Bot is running! Press Ctrl+C to stop.")
        await handler.start_async()

    except KeyboardInterrupt:
        main_logger.info("Received interrupt signal")
    except Exception as e:
        main_logger.error("Failed to start bot", e)
        sys.exit(1)


async def _background_index(rag):
    """
    Run background indexing of channels.

    This indexes all channels the bot is a member of.
    """
    try:
        # Wait a bit for Slack connection to stabilize
        await asyncio.sleep(5)

        main_logger.info("Running initial channel index...")
        channels = await rag.indexer.get_indexable_channels()

        if channels:
            results = await rag.index_all_channels(channels)
            total = sum(results.values())
            main_logger.info(f"Indexed {total} messages across {len(channels)} channels")
        else:
            main_logger.info("No channels to index (bot not in any channels)")

    except Exception as e:
        main_logger.error("Background indexing failed", e)


async def _shutdown(handler, scheduler):
    """
    Graceful shutdown handler.

    Args:
        handler: The Socket Mode handler
        scheduler: The task scheduler
    """
    main_logger.info("Shutting down...")

    # Stop the scheduler
    scheduler.stop()

    # Close the socket connection
    await handler.close_async()

    main_logger.info("Shutdown complete")


def run():
    """
    Synchronous entry point.

    This is called when running with `miniclawd` command.
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()

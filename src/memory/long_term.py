"""
Long-Term Memory
================

File-backed persistent memory storage. Long-term memory:

- Persists across bot restarts
- Stored in markdown files for human readability
- Organized by categories in MEMORY.md
- Daily logs in memory/daily/YYYY-MM-DD.md

File Structure:
    memory/
    ├── MEMORY.md          # Main knowledge base, organized by category
    └── daily/
        ├── 2024-01-30.md  # Daily log files
        └── 2024-01-31.md

MEMORY.md Format:
    # Long-Term Memory

    ## Preferences
    - [2024-01-30] User prefers morning standups at 10am
    - [2024-01-31] Notification style: brief summaries

    ## Decisions
    - [2024-01-30] Decided to use PostgreSQL for the new service

    ## Projects
    - [2024-01-31] Currently working on API v2 refactor

Why Markdown Files?
- Human-readable and editable
- Version controllable with git
- No database setup required
- Easy to backup and restore
- Transparent - users can see exactly what's stored
"""

import asyncio
from datetime import datetime
from pathlib import Path

from src.utils.logger import Logger

logger = Logger("LongTermMemory")


class LongTermMemory:
    """
    File-backed persistent memory.

    Manages two types of storage:
    1. MEMORY.md - Categorized knowledge base
    2. Daily logs - Day-by-day activity records

    Example:
        ltm = LongTermMemory(Path("memory"))

        # Write to categorized memory
        await ltm.write("User prefers 10am meetings", "preferences")

        # Write to today's log
        await ltm.write_daily("Discussed Q1 planning with user")

        # Read all memory content
        content = await ltm.read_all()

        # Search for relevant entries
        results = await ltm.search("meeting preferences")
    """

    def __init__(self, memory_dir: Path):
        """
        Initialize long-term memory.

        Args:
            memory_dir: Path to the memory directory
        """
        self.memory_dir = memory_dir
        self.memory_file = memory_dir / "MEMORY.md"
        self.daily_dir = memory_dir / "daily"

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)

        # Create MEMORY.md if it doesn't exist
        if not self.memory_file.exists():
            self._create_default_memory_file()

    def _create_default_memory_file(self) -> None:
        """Create the default MEMORY.md file."""
        default_content = """# Long-Term Memory

This file stores important information that should persist across sessions.
Organized by category for easy reference.

## Preferences
<!-- User preferences and settings -->

## Decisions
<!-- Important decisions and their context -->

## Projects
<!-- Current and past projects -->

## Notes
<!-- General notes and observations -->
"""
        self.memory_file.write_text(default_content)
        logger.info("Created default MEMORY.md")

    def _get_daily_file(self, date: datetime | None = None) -> Path:
        """
        Get the path to a daily log file.

        Args:
            date: The date for the log file (defaults to today)

        Returns:
            Path to the daily log file
        """
        if date is None:
            date = datetime.now()
        filename = date.strftime("%Y-%m-%d") + ".md"
        return self.daily_dir / filename

    async def write(self, content: str, category: str = "Notes") -> None:
        """
        Write an entry to MEMORY.md under a specific category.

        The entry is appended to the category section with a timestamp.

        Args:
            content: The information to store
            category: The category to file it under

        Example:
            await ltm.write("User likes brief responses", "Preferences")
        """
        # Run file I/O in thread pool to avoid blocking
        await asyncio.to_thread(self._write_sync, content, category)

    def _write_sync(self, content: str, category: str) -> None:
        """Synchronous write operation."""
        # Read current content
        if self.memory_file.exists():
            current = self.memory_file.read_text()
        else:
            self._create_default_memory_file()
            current = self.memory_file.read_text()

        # Format the new entry
        date_str = datetime.now().strftime("%Y-%m-%d")
        entry = f"- [{date_str}] {content}"

        # Find the category section and append
        category_header = f"## {category}"

        if category_header in current:
            # Find where to insert (after the category header)
            lines = current.split("\n")
            new_lines = []
            inserted = False

            for i, line in enumerate(lines):
                new_lines.append(line)

                # If this is our category header, insert after any existing entries
                if line.strip() == category_header and not inserted:
                    # Look ahead for the next section or end
                    # Insert at the first blank line after entries, or before next ##
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j]
                        # If we hit another section, insert before it
                        if next_line.startswith("## "):
                            break
                        # If we hit a blank line after entries, insert there
                        if next_line.strip() == "" and j > i + 1:
                            break
                        j += 1

                    # Insert the entry
                    new_lines.append(entry)
                    inserted = True

            current = "\n".join(new_lines)
        else:
            # Category doesn't exist, add it at the end
            current += f"\n\n{category_header}\n{entry}"

        # Write back
        self.memory_file.write_text(current)
        logger.debug(f"Wrote to long-term memory: {category}")

    async def write_daily(self, content: str) -> None:
        """
        Write an entry to today's daily log.

        Daily logs capture day-to-day activity. Each entry is timestamped.

        Args:
            content: The log entry content
        """
        await asyncio.to_thread(self._write_daily_sync, content)

    def _write_daily_sync(self, content: str) -> None:
        """Synchronous daily log write."""
        daily_file = self._get_daily_file()

        # Create the file with header if it doesn't exist
        if not daily_file.exists():
            date_str = datetime.now().strftime("%Y-%m-%d")
            header = f"# Daily Log - {date_str}\n\n"
            daily_file.write_text(header)

        # Append the entry with timestamp
        time_str = datetime.now().strftime("%H:%M")
        entry = f"- [{time_str}] {content}\n"

        with daily_file.open("a") as f:
            f.write(entry)

        logger.debug("Wrote to daily log")

    async def read_all(self) -> str:
        """
        Read all content from MEMORY.md.

        Returns:
            The full contents of MEMORY.md
        """
        return await asyncio.to_thread(self._read_all_sync)

    def _read_all_sync(self) -> str:
        """Synchronous read of MEMORY.md."""
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text()

    async def read_daily(self, date: datetime | None = None) -> str:
        """
        Read a daily log file.

        Args:
            date: The date to read (defaults to today)

        Returns:
            The contents of the daily log, or empty string if none
        """
        return await asyncio.to_thread(self._read_daily_sync, date)

    def _read_daily_sync(self, date: datetime | None = None) -> str:
        """Synchronous read of daily log."""
        daily_file = self._get_daily_file(date)
        if not daily_file.exists():
            return ""
        return daily_file.read_text()

    async def search(self, query: str) -> list[str]:
        """
        Search long-term memory for relevant entries.

        This is a simple keyword-based search. For semantic search,
        use the RAG system instead.

        Args:
            query: Keywords to search for

        Returns:
            List of matching lines from MEMORY.md
        """
        return await asyncio.to_thread(self._search_sync, query)

    def _search_sync(self, query: str) -> list[str]:
        """Synchronous search operation."""
        if not self.memory_file.exists():
            return []

        content = self.memory_file.read_text()
        query_lower = query.lower()
        keywords = query_lower.split()

        results = []
        for line in content.split("\n"):
            line_lower = line.lower()
            # Match if any keyword is found
            if any(kw in line_lower for kw in keywords):
                # Only include entry lines (starting with -)
                if line.strip().startswith("-"):
                    results.append(line.strip())

        return results

    async def get_recent_entries(self, days: int = 7) -> list[str]:
        """
        Get entries from the last N days of daily logs.

        Args:
            days: Number of days to look back

        Returns:
            List of entries from recent daily logs
        """
        return await asyncio.to_thread(self._get_recent_entries_sync, days)

    def _get_recent_entries_sync(self, days: int) -> list[str]:
        """Synchronous recent entries retrieval."""
        from datetime import timedelta

        entries = []
        today = datetime.now()

        for i in range(days):
            date = today - timedelta(days=i)
            daily_file = self._get_daily_file(date)

            if daily_file.exists():
                content = daily_file.read_text()
                # Extract entry lines
                for line in content.split("\n"):
                    if line.strip().startswith("-"):
                        entries.append(line.strip())

        return entries

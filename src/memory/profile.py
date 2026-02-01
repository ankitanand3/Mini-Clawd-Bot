"""
Profile Manager
===============

Manages the profile/context files:
- USER.md: User preferences and information
- SOUL.md: Bot personality and behavior guidelines
- TOOLS.md: Environment and tool-specific notes

These files are different from MEMORY.md in that they contain
structured, curated information rather than a log of events.

File Purposes:

USER.md - Information about the user:
    - Name and contact preferences
    - Communication style preferences
    - Important dates/reminders
    - Channel preferences

SOUL.md - Bot personality definition:
    - Communication tone and style
    - Behavioral guidelines
    - Response patterns
    - Things to avoid

TOOLS.md - Environment configuration:
    - API configurations
    - Tool-specific settings
    - Device/account information
    - Integration notes
"""

from pathlib import Path

from src.utils.logger import Logger

logger = Logger("Profile")


# Default content for profile files when they don't exist
DEFAULT_USER = """# User Profile

Information about the user for personalized assistance.

## Basic Info
- Name: [Not set]
- Timezone: [Not set]

## Preferences
- Communication style: [Not set]
- Preferred notification times: [Not set]

## Important Notes
<!-- Add important information about the user here -->
"""

DEFAULT_SOUL = """# MiniClawd Bot Personality

Guidelines for how I should behave and communicate.

## Core Traits
- Helpful and proactive
- Clear and concise
- Professional but friendly
- Honest about limitations

## Communication Style
- Use clear, direct language
- Break complex topics into digestible pieces
- Ask clarifying questions when needed
- Provide actionable suggestions

## Things I Do
- Help with Slack channel management
- Summarize conversations
- Set reminders and schedule messages
- Create GitHub issues and Notion pages
- Remember important information

## Things I Avoid
- Being overly verbose
- Making assumptions without asking
- Sharing private information publicly
- Taking actions without confirmation on important matters

## Response Format
- Keep responses focused and relevant
- Use markdown formatting when helpful
- Include next steps or suggestions when appropriate
"""

DEFAULT_TOOLS = """# Tools & Environment

Configuration and notes about available tools and integrations.

## Slack Integration
- Connected to workspace
- Available commands: mention me in any channel or DM

## OpenAI Integration
- Model: GPT-4 Turbo
- Embeddings: text-embedding-3-small

## GitHub Integration
- Status: [Configure GITHUB_TOKEN to enable]
- Default repo: [Not set]

## Notion Integration
- Status: [Configure NOTION_TOKEN to enable]
- Default parent page: [Not set]

## Notes
<!-- Add tool-specific notes and configurations here -->
"""


class ProfileManager:
    """
    Manages profile and context files.

    Profile files contain curated, structured information that helps
    the bot understand:
    - Who the user is (USER.md)
    - How to behave (SOUL.md)
    - What tools are available (TOOLS.md)

    These files are loaded into context when generating responses.

    Example:
        pm = ProfileManager(Path("memory"))

        # Get the bot's personality guidelines
        soul = pm.get_soul()

        # Get user preferences
        user = pm.get_user()

        # Update user preferences
        pm.update_user("## Preferences\\n- Style: Brief and technical")
    """

    def __init__(self, memory_dir: Path):
        """
        Initialize the profile manager.

        Args:
            memory_dir: Path to the memory directory
        """
        self.memory_dir = memory_dir
        self.user_file = memory_dir / "USER.md"
        self.soul_file = memory_dir / "SOUL.md"
        self.tools_file = memory_dir / "TOOLS.md"

        # Ensure files exist with defaults
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Create profile files with defaults if they don't exist."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        if not self.user_file.exists():
            self.user_file.write_text(DEFAULT_USER)
            logger.info("Created default USER.md")

        if not self.soul_file.exists():
            self.soul_file.write_text(DEFAULT_SOUL)
            logger.info("Created default SOUL.md")

        if not self.tools_file.exists():
            self.tools_file.write_text(DEFAULT_TOOLS)
            logger.info("Created default TOOLS.md")

    def get_user(self) -> str:
        """
        Get user profile content.

        Returns:
            Contents of USER.md
        """
        return self._read_file(self.user_file)

    def get_soul(self) -> str:
        """
        Get bot personality/behavior guidelines.

        Returns:
            Contents of SOUL.md
        """
        return self._read_file(self.soul_file)

    def get_tools(self) -> str:
        """
        Get tools/environment context.

        Returns:
            Contents of TOOLS.md
        """
        return self._read_file(self.tools_file)

    def _read_file(self, path: Path) -> str:
        """Read a profile file."""
        if not path.exists():
            return ""
        return path.read_text()

    def update_user(self, content: str) -> None:
        """
        Update user profile content.

        This replaces the entire file content.

        Args:
            content: New content for USER.md
        """
        self.user_file.write_text(content)
        logger.info("Updated USER.md")

    def update_soul(self, content: str) -> None:
        """
        Update bot personality content.

        This replaces the entire file content.

        Args:
            content: New content for SOUL.md
        """
        self.soul_file.write_text(content)
        logger.info("Updated SOUL.md")

    def update_tools(self, content: str) -> None:
        """
        Update tools/environment content.

        This replaces the entire file content.

        Args:
            content: New content for TOOLS.md
        """
        self.tools_file.write_text(content)
        logger.info("Updated TOOLS.md")

    def append_to_user(self, section: str, entry: str) -> None:
        """
        Append an entry to a section in USER.md.

        Args:
            section: The section header (e.g., "## Preferences")
            entry: The entry to append
        """
        self._append_to_section(self.user_file, section, entry)

    def _append_to_section(self, file: Path, section: str, entry: str) -> None:
        """Append entry to a section in a profile file."""
        content = file.read_text()

        if section in content:
            # Find the section and append
            lines = content.split("\n")
            new_lines = []

            for i, line in enumerate(lines):
                new_lines.append(line)
                if line.strip() == section:
                    # Add the entry after the section header
                    new_lines.append(entry)

            content = "\n".join(new_lines)
        else:
            # Section doesn't exist, add it at the end
            content += f"\n\n{section}\n{entry}"

        file.write_text(content)

    def get_all_context(self) -> str:
        """
        Get all profile context combined.

        Useful for including full context in LLM prompts.

        Returns:
            Combined content of all profile files
        """
        sections = []

        # Add SOUL first (bot identity)
        soul = self.get_soul()
        if soul:
            sections.append("### Bot Personality (SOUL.md)\n" + soul)

        # Add USER (user info)
        user = self.get_user()
        if user:
            sections.append("### User Profile (USER.md)\n" + user)

        # Add TOOLS (environment)
        tools = self.get_tools()
        if tools:
            sections.append("### Environment (TOOLS.md)\n" + tools)

        return "\n\n---\n\n".join(sections)

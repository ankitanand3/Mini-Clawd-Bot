"""
Configuration Management
========================

Centralized configuration for the entire application. All environment
variables are validated and typed here, making it easy to:

1. See all configuration options in one place
2. Get type-safe access to configuration values
3. Fail fast if required configuration is missing

Why centralize configuration?
- Prevents scattered os.getenv() calls throughout the codebase
- Makes it clear which config is required vs optional
- Provides default values in one place
- Enables type checking and IDE autocomplete

Usage:
    from src.utils.config import get_config

    config = get_config()
    print(config.slack.bot_token)
    print(config.openai.model)
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _required(name: str) -> str:
    """
    Get a required environment variable.

    Args:
        name: The environment variable name

    Returns:
        The value of the environment variable

    Raises:
        ValueError: If the variable is not set
    """
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Missing required environment variable: {name}\n"
            f"Please ensure {name} is set in your .env file."
        )
    return value


def _optional(name: str, default: str) -> str:
    """
    Get an optional environment variable with a default.

    Args:
        name: The environment variable name
        default: Default value if not set

    Returns:
        The value or the default
    """
    return os.getenv(name, default)


def _optional_int(name: str, default: int) -> int:
    """
    Get an optional integer environment variable.

    Args:
        name: The environment variable name
        default: Default value if not set or invalid

    Returns:
        The integer value or the default
    """
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"Warning: {name} is not a valid integer, using default: {default}")
        return default


def _optional_bool(name: str, default: bool) -> bool:
    """
    Get an optional boolean environment variable.

    Args:
        name: The environment variable name
        default: Default value if not set

    Returns:
        True if value is 'true' (case-insensitive), False otherwise
    """
    value = os.getenv(name)
    if not value:
        return default
    return value.lower() == "true"


# ==============================================================================
# Configuration Dataclasses
# ==============================================================================
# We use dataclasses to define the shape of our configuration.
# This provides:
# - Clear structure
# - Type hints for IDE autocomplete
# - Immutability (frozen=True)

@dataclass(frozen=True)
class SlackConfig:
    """Slack API configuration."""
    bot_token: str      # xoxb-... token for bot operations
    app_token: str      # xapp-... token for Socket Mode
    signing_secret: str # For verifying Slack requests


@dataclass(frozen=True)
class OpenAIConfig:
    """OpenAI API configuration."""
    api_key: str           # sk-... API key
    model: str             # Model for chat completions
    embedding_model: str   # Model for embeddings


@dataclass(frozen=True)
class GitHubConfig:
    """GitHub API configuration (optional)."""
    token: str | None       # ghp-... Personal Access Token
    default_repo: str | None # Default repo for issue creation


@dataclass(frozen=True)
class NotionConfig:
    """Notion API configuration (optional)."""
    token: str | None            # secret_... Integration token
    default_parent_page: str | None # Default parent for new pages


@dataclass(frozen=True)
class RAGConfig:
    """RAG (Retrieval Augmented Generation) configuration."""
    messages_per_channel: int   # Max messages to index per channel
    index_frequency_hours: int  # How often to re-index
    min_message_length: int     # Min length to include in index


@dataclass(frozen=True)
class MemoryConfig:
    """Memory system configuration."""
    directory: Path              # Path to memory files
    enable_heartbeat: bool       # Enable periodic checks
    heartbeat_interval_minutes: int # Heartbeat frequency


@dataclass(frozen=True)
class Config:
    """
    Root configuration object.

    Contains all configuration sections. Access via:
        config = get_config()
        config.slack.bot_token
        config.openai.model
        config.rag.messages_per_channel
    """
    slack: SlackConfig
    openai: OpenAIConfig
    github: GitHubConfig
    notion: NotionConfig
    rag: RAGConfig
    memory: MemoryConfig
    log_level: str


def load_config() -> Config:
    """
    Load and validate all configuration from environment.

    This function is called once at startup. It:
    1. Loads .env file
    2. Validates required configuration
    3. Sets defaults for optional configuration
    4. Returns a fully typed Config object

    Returns:
        Config: The validated configuration

    Raises:
        ValueError: If required configuration is missing
    """
    # Load .env file from project root
    # This searches up the directory tree for .env
    load_dotenv()

    # Determine the project root (where memory/ and data/ live)
    # This assumes config.py is in src/utils/
    project_root = Path(__file__).parent.parent.parent

    return Config(
        slack=SlackConfig(
            bot_token=_required("SLACK_BOT_TOKEN"),
            app_token=_required("SLACK_APP_TOKEN"),
            signing_secret=_required("SLACK_SIGNING_SECRET"),
        ),
        openai=OpenAIConfig(
            api_key=_required("OPENAI_API_KEY"),
            model=_optional("OPENAI_MODEL", "gpt-4-turbo-preview"),
            embedding_model=_optional("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        ),
        github=GitHubConfig(
            token=os.getenv("GITHUB_TOKEN"),
            default_repo=os.getenv("GITHUB_DEFAULT_REPO"),
        ),
        notion=NotionConfig(
            token=os.getenv("NOTION_TOKEN"),
            default_parent_page=os.getenv("NOTION_DEFAULT_PARENT_PAGE"),
        ),
        rag=RAGConfig(
            messages_per_channel=_optional_int("RAG_MESSAGES_PER_CHANNEL", 200),
            index_frequency_hours=_optional_int("RAG_INDEX_FREQUENCY_HOURS", 6),
            min_message_length=_optional_int("RAG_MIN_MESSAGE_LENGTH", 10),
        ),
        memory=MemoryConfig(
            directory=project_root / _optional("MEMORY_DIR", "memory"),
            enable_heartbeat=_optional_bool("ENABLE_HEARTBEAT", True),
            heartbeat_interval_minutes=_optional_int("HEARTBEAT_INTERVAL_MINUTES", 60),
        ),
        log_level=_optional("LOG_LEVEL", "info"),
    )


# ==============================================================================
# Singleton Pattern
# ==============================================================================
# We use a singleton to ensure configuration is loaded once and shared.
# This is a common pattern for configuration objects.

_config_instance: Config | None = None


def get_config() -> Config:
    """
    Get the singleton configuration instance.

    The configuration is loaded on first access and cached for subsequent calls.
    This ensures:
    - Configuration validation happens early
    - All modules get the same config instance
    - No repeated parsing of environment variables

    Returns:
        Config: The application configuration
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = load_config()
    return _config_instance


# ==============================================================================
# Helper Functions
# ==============================================================================

def is_github_configured() -> bool:
    """Check if GitHub integration is configured."""
    config = get_config()
    return config.github.token is not None


def is_notion_configured() -> bool:
    """Check if Notion integration is configured."""
    config = get_config()
    return config.notion.token is not None

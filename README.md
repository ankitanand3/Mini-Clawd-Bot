# MiniClawd Bot - Intelligent Slack Assistant

> A comprehensive Slack bot built with an agent-based architecture, featuring multi-layer memory, RAG knowledge base, and MCP tool integrations.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Core Systems](#core-systems)
4. [Memory System](#memory-system)
5. [RAG Knowledge Base](#rag-knowledge-base)
6. [MCP Tools](#mcp-tools)
7. [Setup Guide](#setup-guide)
8. [Usage Examples](#usage-examples)
9. [Educational Notes](#educational-notes)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER REQUEST                                    │
│                    (via Slack mention or DM)                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SLACK INTEGRATION                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Bolt App    │  │ Event       │  │ Message     │  │ Socket      │        │
│  │ Instance    │  │ Handlers    │  │ Parser      │  │ Mode        │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT CORE                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Context Assembly                              │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐        │   │
│  │  │ Memory    │  │ RAG       │  │ Convo     │  │ Tool      │        │   │
│  │  │ Recall    │  │ Context   │  │ History   │  │ Definitions│       │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         LLM Processing                               │   │
│  │  • Analyze user intent                                               │   │
│  │  • Determine if RAG needed                                           │   │
│  │  • Select appropriate tools                                          │   │
│  │  • Generate response                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Tool Executor                                 │   │
│  │  • Execute selected tools                                            │   │
│  │  • Handle tool results                                               │   │
│  │  • Loop until completion                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MCP TOOLS                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Slack       │  │ GitHub      │  │ Notion      │  │ Scheduler   │        │
│  │ Tools       │  │ MCP Server  │  │ MCP Server  │  │ Tools       │        │
│  │             │  │             │  │             │  │             │        │
│  │ • Fetch     │  │ • Create    │  │ • Create    │  │ • Reminders │        │
│  │   Messages  │  │   Issues    │  │   Pages     │  │ • Schedule  │        │
│  │ • Post      │  │ • Search    │  │ • Update    │  │   Messages  │        │
│  │ • Summarize │  │   Code      │  │ • Query     │  │ • Recurring │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MEMORY SYSTEM                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Layer 1: SHORT-TERM (in-memory)                                      │   │
│  │ • Current conversation context                                       │   │
│  │ • Message history within session                                     │   │
│  │ • Cleared on session end                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Layer 2: WORKING MEMORY (session-scoped)                             │   │
│  │ • Ad-hoc notes during session                                        │   │
│  │ • Temporary decisions and context                                    │   │
│  │ • Not persisted unless explicitly saved                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Layer 3: FILE-BACKED LONG-TERM                                       │   │
│  │ • MEMORY.md - Curated important information                          │   │
│  │ • memory/YYYY-MM-DD.md - Daily logs                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Layer 4: PROFILE & CONTEXT FILES                                     │   │
│  │ • USER.md - User preferences and information                         │   │
│  │ • SOUL.md - Bot behavior and personality                             │   │
│  │ • TOOLS.md - Environment and tool notes                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Layer 5: TASK STATE                                                  │   │
│  │ • heartbeat-state.json - Scheduled task timestamps                   │   │
│  │ • Cron jobs for recurring tasks                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAG KNOWLEDGE BASE                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Vector Store                                  │   │
│  │  • Indexes past 200 messages per channel                             │   │
│  │  • Configurable indexing frequency                                   │   │
│  │  • Semantic search using embeddings                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Indexer Service                               │   │
│  │  • Background indexing of joined channels                            │   │
│  │  • Incremental updates                                               │   │
│  │  • Metadata preservation                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
Mini_Clawd_bot/
├── README.md                    # This file - Architecture documentation
├── pyproject.toml              # Python project configuration (PEP 621)
├── requirements.txt            # Dependencies for pip install
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
│
├── src/                        # Source code
│   ├── __init__.py
│   ├── main.py                # Main entry point - Starts the bot
│   │
│   ├── agent/                  # 🧠 Agent System (the brain)
│   │   ├── __init__.py
│   │   ├── core.py            # Core agent orchestration logic
│   │   ├── context.py         # Context assembly for LLM
│   │   └── tools_executor.py  # Tool execution and result handling
│   │
│   ├── memory/                 # 📝 Memory System (multi-layer)
│   │   ├── __init__.py        # Memory manager (facade pattern)
│   │   ├── short_term.py      # In-memory conversation context
│   │   ├── working.py         # Session-scoped working memory
│   │   ├── long_term.py       # File-backed persistent memory
│   │   ├── profile.py         # Profile files (USER, SOUL, TOOLS)
│   │   └── recall.py          # Intelligent memory recall
│   │
│   ├── rag/                    # 🔍 RAG Knowledge Base
│   │   ├── __init__.py        # RAG manager
│   │   ├── vectorstore.py     # Vector storage implementation
│   │   ├── embeddings.py      # Embedding generation
│   │   └── indexer.py         # Channel message indexer
│   │
│   ├── tools/                  # 🔧 MCP Tools
│   │   ├── __init__.py        # Tool registry and definitions
│   │   ├── slack_tools.py     # Slack operations (fetch, post, summarize)
│   │   ├── github_tools.py    # GitHub MCP server (issues, code search)
│   │   ├── notion_tools.py    # Notion MCP server (pages, databases)
│   │   └── scheduler.py       # Reminders and scheduled messages
│   │
│   ├── slack/                  # 💬 Slack Integration
│   │   ├── __init__.py
│   │   ├── app.py             # Slack Bolt app initialization
│   │   └── handlers.py        # Event and message handlers
│   │
│   └── utils/                  # 🛠️ Utilities
│       ├── __init__.py
│       ├── logger.py          # Structured logging
│       └── config.py          # Configuration management
│
├── memory/                     # 📁 Memory Storage (file-backed)
│   ├── MEMORY.md              # Curated long-term memory
│   ├── USER.md                # User preferences and info
│   ├── SOUL.md                # Bot behavior/personality
│   ├── TOOLS.md               # Environment and tool notes
│   ├── heartbeat_state.json   # Scheduled task state
│   └── daily/                 # Daily log files
│       └── .gitkeep
│
└── data/                       # 📊 Data Storage
    └── vectorstore/           # RAG vector storage
        └── .gitkeep
```

---

## Core Systems

### 1. Agent Core (`src/agent/`)

The agent is the brain of the system. It orchestrates all operations:

```python
# Simplified flow
async def process_request(user_message: str) -> str:
    # 1. Assemble context from all sources
    context = await assemble_context(user_message)

    # 2. Determine if RAG is needed
    if should_use_rag(user_message):
        context.rag_results = await rag.search(user_message)

    # 3. Send to LLM with tools
    response = await llm.chat(
        messages=context.messages,
        tools=get_available_tools()
    )

    # 4. Execute any tool calls (loop until done)
    while response.tool_calls:
        results = await execute_tools(response.tool_calls)
        response = await llm.continue_with(results)

    # 5. Return final response
    return response.content
```

**Key Design Decisions:**
- **Tool Loop**: The agent can call tools multiple times until it has enough information
- **Context Assembly**: Memory, RAG, and conversation history are combined intelligently
- **RAG Decision**: Agent decides whether to search the knowledge base based on the query

### 2. Memory System (`src/memory/`)

A sophisticated multi-layer memory system:

| Layer | Storage | Lifetime | Purpose |
|-------|---------|----------|---------|
| Short-term | In-memory dict | Session | Current conversation context |
| Working | In-memory dict | Session | Ad-hoc notes, temporary decisions |
| Long-term | MEMORY.md + daily/ | Permanent | Important facts, commitments |
| Profile | USER.md, SOUL.md | Permanent | User prefs, bot personality |
| Task State | heartbeat_state.json | Permanent | Scheduled task tracking |

**Memory Recall Process:**
```python
async def recall(query: str) -> MemoryContext:
    # 1. Always include recent short-term memory
    recent_context = short_term.get_recent(10)

    # 2. Search long-term memory for relevant entries
    long_term_results = await search_memory_files(query)

    # 3. Load profile files if relevant
    profile_context = load_relevant_profiles(query)

    # 4. Return combined context (keeping within token limits)
    return combine_and_truncate(recent_context, long_term_results, profile_context)
```

### 3. RAG Knowledge Base (`src/rag/`)

Vector-based semantic search over Slack channel history:

**Indexing Strategy:**
- Index the most recent 200 messages per channel
- Re-index periodically (configurable frequency)
- Store message metadata (author, timestamp, channel)

**Search Flow:**
```python
async def search(query: str) -> list[RAGResult]:
    # 1. Generate embedding for query
    query_embedding = await generate_embedding(query)

    # 2. Find similar vectors
    results = vector_store.similarity_search(query_embedding, top_k=10)

    # 3. Return with metadata
    return [
        RAGResult(
            content=r.content,
            channel=r.metadata["channel"],
            author=r.metadata["author"],
            timestamp=r.metadata["timestamp"],
            score=r.similarity
        )
        for r in results
    ]
```

### 4. MCP Tools (`src/tools/`)

Tools follow the Model Context Protocol pattern:

```python
@dataclass
class MCPTool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    execute: Callable[[dict], Awaitable[ToolResult]]
```

**Available Tools:**

| Tool | Description | Use Case |
|------|-------------|----------|
| `slack_fetch_messages` | Fetch messages from a channel | "Summarize #general" |
| `slack_post_message` | Post a message to a channel | Reply drafting |
| `slack_schedule_message` | Schedule a future message | "Post at 10am daily" |
| `github_create_issue` | Create a GitHub issue | Issue tracking |
| `github_search_code` | Search code in repos | Code reference |
| `notion_create_page` | Create a Notion page | Documentation |
| `notion_append_content` | Add to existing page | Updates |
| `set_reminder` | Set a personal reminder | "Remind me in 5 min" |
| `memory_write` | Write to long-term memory | "Remember this" |

---

## Memory System Deep Dive

### File Structure

```
memory/
├── MEMORY.md              # Curated knowledge
│   │
│   │   Format:
│   │   ## [Category]
│   │   - [Date] Key fact or decision
│   │
├── USER.md                # User preferences
│   │
│   │   Format:
│   │   # User Profile
│   │   - Name: ...
│   │   - Preferences: ...
│   │   - Channels: ...
│   │
├── SOUL.md                # Bot personality
│   │
│   │   Defines:
│   │   - Communication style
│   │   - Behavior guidelines
│   │   - Response patterns
│   │
├── TOOLS.md               # Environment info
│   │
│   │   Contains:
│   │   - API configurations
│   │   - Device/account info
│   │   - Tool-specific notes
│   │
├── heartbeat_state.json   # Task tracking
│   │
│   │   {
│   │     "last_heartbeat": "2024-...",
│   │     "scheduled_tasks": [...],
│   │     "reminders": [...]
│   │   }
│   │
└── daily/
    └── YYYY-MM-DD.md      # Daily logs
        │
        │   Format:
        │   # Daily Log - YYYY-MM-DD
        │   ## Conversations
        │   ## Decisions
        │   ## Notes
```

### When Memory is Written

| Event | What's Written | Where |
|-------|---------------|-------|
| User states preference | Preference detail | USER.md |
| Important decision made | Decision + context | MEMORY.md |
| Daily activity | Summary | daily/YYYY-MM-DD.md |
| Scheduled task created | Task details | heartbeat_state.json |
| Tool configuration | Config notes | TOOLS.md |

### Memory Privacy

- MEMORY.md is only accessed in 1:1 DMs (not group channels)
- Sensitive data never leaves local storage
- User can review/edit all memory files

---

## RAG Knowledge Base Deep Dive

### Why RAG?

The RAG (Retrieval Augmented Generation) system allows the bot to:
1. Answer questions about past channel discussions
2. Find relevant context for summarization
3. Recall specific conversations or decisions

### When RAG is Used

The agent decides to use RAG when:
- User asks about channel history ("What did we discuss...")
- Summarization is requested ("Summarize the last 24 hours")
- Context search is implied ("Any issues reported in #bugs?")

### Indexing Configuration

```python
RAG_CONFIG = {
    # Maximum messages to index per channel
    "messages_per_channel": 200,

    # How often to re-index (in hours)
    "indexing_frequency": 6,

    # Minimum message length to index
    "min_message_length": 10,

    # Embedding model
    "embedding_model": "text-embedding-3-small"
}
```

---

## Setup Guide

### Prerequisites

- Python 3.11+
- Slack workspace with admin access
- OpenAI API key (for embeddings and LLM)
- GitHub token (optional, for GitHub integration)
- Notion integration (optional, for Notion integration)

### 1. Environment Setup

```bash
# Clone and create virtual environment
cd Mini_Clawd_bot
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env`:

```env
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-key

# GitHub Configuration (optional)
GITHUB_TOKEN=ghp-your-github-token

# Notion Configuration (optional)
NOTION_TOKEN=secret_your-notion-token
```

### 3. Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Create New App → From scratch
3. Enable **Socket Mode** (Settings → Socket Mode)
4. Add **Bot Token Scopes** (OAuth & Permissions):
   - `app_mentions:read`
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `chat:write.customize`
   - `im:history`
   - `im:read`
   - `im:write`
   - `users:read`
5. Enable **Events** (Event Subscriptions):
   - `app_mention`
   - `message.im`
6. Install to workspace
7. Copy tokens to `.env`

### 4. Initialize Memory Files

The bot will create default memory files on first run, or you can customize them:

```bash
# Edit to customize bot personality
nano memory/SOUL.md

# Add your preferences
nano memory/USER.md
```

### 5. Run the Bot

```bash
# Development
python -m src.main

# Or with auto-reload (using watchdog)
pip install watchdog
watchmedo auto-restart --patterns="*.py" --recursive -- python -m src.main
```

---

## Usage Examples

### Channel Summarization

```
@MiniClawd Go to #engineering and summarize the last 24 hours
```

Response:
> Here's a summary of #engineering from the past 24 hours:
>
> **Key Discussions:**
> - Database migration plan was finalized (by @alice)
> - New CI/CD pipeline is ready for review (by @bob)
>
> **Action Items:**
> - Review PR #142 before EOD
> - Schedule deployment for Friday
>
> **Draft Reply:**
> "Thanks for the updates! I'll review PR #142 today and confirm the Friday deployment window."

### Set a Reminder

```
@MiniClawd Remind me to send the report in 30 minutes
```

Response:
> Reminder set! I'll ping you in 30 minutes about sending the report.

### Scheduled Messages

```
@MiniClawd Send a welcome message to #general every morning at 9 AM
```

Response:
> Scheduled! I'll post a welcome message to #general at 9:00 AM daily.
>
> Default message: "Good morning team! Hope everyone has a productive day!"
>
> Would you like to customize the message?

### GitHub Issue Creation

```
@MiniClawd Scan #bugs for issues and create GitHub issues on myorg/myrepo
```

Response:
> I found 3 potential issues in #bugs:
>
> 1. **Login timeout issue** - Created as [#142](link)
> 2. **API rate limiting** - Created as [#143](link)
> 3. **Mobile rendering bug** - Created as [#144](link)

### Notion Documentation

```
@MiniClawd Create a Notion page summarizing today's #product discussion
```

Response:
> Created Notion page: [Product Discussion - Jan 31, 2024](link)
>
> Contents include:
> - Meeting notes summary
> - Key decisions
> - Action items
> - Next steps

---

## Educational Notes

### Why This Architecture?

**Agent-Based Design:**
- Flexibility: Agent can combine tools in any order
- Extensibility: Easy to add new tools
- Intelligence: LLM decides what actions to take

**Multi-Layer Memory:**
- Mimics human memory (short-term → long-term)
- File-based for transparency and debuggability
- Separate concerns (profile vs logs vs state)

**RAG Over Full Context:**
- Slack history can be huge; RAG finds relevant parts
- Semantic search beats keyword matching
- Embeddings capture meaning, not just words

### Key Design Patterns

1. **Facade Pattern** (`memory/__init__.py`): Single interface for complex memory subsystem
2. **Registry Pattern** (`tools/__init__.py`): Central tool registration and discovery
3. **Strategy Pattern** (`rag/embeddings.py`): Swappable embedding providers
4. **Observer Pattern** (`slack/handlers.py`): Event-driven message handling

### Performance Considerations

- **Token Budget**: Context assembly respects LLM token limits
- **Lazy Loading**: Memory files loaded only when needed
- **Background Indexing**: RAG indexing doesn't block requests
- **Caching**: Embeddings cached to reduce API calls

### Security Considerations

- **Token Storage**: All tokens in `.env`, never committed
- **Memory Privacy**: Personal memory not exposed in group chats
- **Input Validation**: Tool parameters validated before execution
- **Rate Limiting**: Respect Slack and external API rate limits

---

## Extending the Bot

### Adding a New Tool

1. Create tool in `src/tools/`:

```python
# src/tools/my_tool.py
from src.tools import MCPTool, ToolResult, tool_registry

async def execute_my_tool(params: dict) -> ToolResult:
    """Implementation of my tool."""
    # Your logic here
    return ToolResult(success=True, data={"result": "value"})

my_tool = MCPTool(
    name="my_tool",
    description="What this tool does",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."}
        },
        "required": ["param1"]
    },
    execute=execute_my_tool
)

# Register the tool
tool_registry.register(my_tool)
```

2. Import in `src/tools/__init__.py`:

```python
from src.tools.my_tool import my_tool
```

### Adding a New Memory Layer

1. Create layer file in `src/memory/`
2. Implement the `MemoryLayer` protocol
3. Register in `src/memory/__init__.py`

---

## License

MIT License - Feel free to use this as a learning resource or starting point for your own projects.

---

## Contributing

This project is designed to be educational. Feel free to:
- Open issues for questions
- Submit PRs with improvements
- Fork for your own experiments

---

*Built as an educational example of AI agent architecture*

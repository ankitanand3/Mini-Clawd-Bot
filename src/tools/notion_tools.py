"""
Notion MCP Tools
================

Tools for interacting with Notion: creating pages, appending content.

These tools allow the agent to:
- Create new pages for documentation
- Append content to existing pages
- Query databases (future)

Notion API Notes:
- Uses httpx for async HTTP requests
- Requires an Integration Token
- Pages must be shared with the integration to be accessible

MCP Server Pattern:
    This module follows the MCP pattern for tool definition and execution.
"""

import httpx
from datetime import datetime

from src.tools import MCPTool, ToolResult, tool_registry
from src.utils.config import get_config, is_notion_configured
from src.utils.logger import Logger

logger = Logger("NotionTools")

# Notion API base URL
NOTION_API = "https://api.notion.com/v1"


async def _make_notion_request(
    method: str,
    endpoint: str,
    data: dict | None = None
) -> dict | None:
    """
    Make an authenticated request to the Notion API.

    Args:
        method: HTTP method (GET, POST, PATCH)
        endpoint: API endpoint
        data: Request body

    Returns:
        Response JSON or None if failed
    """
    config = get_config()

    if not config.notion.token:
        return None

    headers = {
        "Authorization": f"Bearer {config.notion.token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    url = f"{NOTION_API}{endpoint}"

    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=data)
        elif method == "PATCH":
            response = await client.patch(url, headers=headers, json=data)
        else:
            response = await client.request(method, url, headers=headers, json=data)

        if response.status_code >= 400:
            logger.error(f"Notion API error: {response.status_code} - {response.text}")
            return None

        return response.json()


def _text_to_blocks(text: str) -> list[dict]:
    """
    Convert plain text to Notion blocks.

    Splits text into paragraphs and creates paragraph blocks.

    Args:
        text: Plain text content

    Returns:
        List of Notion block objects
    """
    blocks = []
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        if not para.strip():
            continue

        # Check for headings (lines starting with #)
        lines = para.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("### "):
                blocks.append({
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                    }
                })
            elif line.startswith("## "):
                blocks.append({
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                    }
                })
            elif line.startswith("# "):
                blocks.append({
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            else:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    }
                })

    return blocks


# ==============================================================================
# Tool: Create Page
# ==============================================================================

async def _create_page(params: dict) -> ToolResult:
    """
    Create a new Notion page.

    Creates a page under the specified parent (or default parent).
    """
    if not is_notion_configured():
        return ToolResult(
            success=False,
            error="Notion is not configured. Set NOTION_TOKEN in .env"
        )

    title = params.get("title")
    content = params.get("content", "")
    parent_page_id = params.get("parent_page_id")

    if not title:
        return ToolResult(success=False, error="Title is required")

    # Use default parent if not specified
    if not parent_page_id:
        config = get_config()
        parent_page_id = config.notion.default_parent_page

    if not parent_page_id:
        return ToolResult(
            success=False,
            error="Parent page ID is required. Set NOTION_DEFAULT_PARENT_PAGE or provide parent_page_id"
        )

    try:
        # Build the page creation request
        data = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {
                    "title": [
                        {"type": "text", "text": {"content": title}}
                    ]
                }
            }
        }

        # Add content as children blocks
        if content:
            data["children"] = _text_to_blocks(content)

        result = await _make_notion_request("POST", "/pages", data)

        if result is None:
            return ToolResult(success=False, error="Failed to create page")

        return ToolResult(success=True, data={
            "page_id": result.get("id"),
            "url": result.get("url"),
            "title": title,
            "created": True
        })

    except Exception as e:
        logger.error(f"Error creating Notion page: {title}", e)
        return ToolResult(success=False, error=str(e))


create_page_tool = MCPTool(
    name="notion_create_page",
    description="Create a new Notion page. Use this to document discussions, meeting notes, or summaries.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Page title"
            },
            "content": {
                "type": "string",
                "description": "Page content (markdown-like formatting supported)"
            },
            "parent_page_id": {
                "type": "string",
                "description": "Parent page ID (uses default if not specified)"
            }
        },
        "required": ["title"]
    },
    execute=_create_page
)


# ==============================================================================
# Tool: Append to Page
# ==============================================================================

async def _append_to_page(params: dict) -> ToolResult:
    """
    Append content to an existing Notion page.
    """
    if not is_notion_configured():
        return ToolResult(
            success=False,
            error="Notion is not configured. Set NOTION_TOKEN in .env"
        )

    page_id = params.get("page_id")
    content = params.get("content")

    if not page_id or not content:
        return ToolResult(success=False, error="Page ID and content are required")

    try:
        # Convert content to blocks
        blocks = _text_to_blocks(content)

        # Append blocks to the page
        endpoint = f"/blocks/{page_id}/children"
        data = {"children": blocks}

        result = await _make_notion_request("PATCH", endpoint, data)

        if result is None:
            return ToolResult(success=False, error="Failed to append content")

        return ToolResult(success=True, data={
            "page_id": page_id,
            "blocks_added": len(blocks),
            "appended": True
        })

    except Exception as e:
        logger.error(f"Error appending to Notion page: {page_id}", e)
        return ToolResult(success=False, error=str(e))


append_to_page_tool = MCPTool(
    name="notion_append_content",
    description="Append content to an existing Notion page. Use this to add updates or additional information.",
    parameters={
        "type": "object",
        "properties": {
            "page_id": {
                "type": "string",
                "description": "The Notion page ID to append to"
            },
            "content": {
                "type": "string",
                "description": "Content to append (markdown-like formatting supported)"
            }
        },
        "required": ["page_id", "content"]
    },
    execute=_append_to_page
)


# ==============================================================================
# Tool: Search Pages
# ==============================================================================

async def _search_pages(params: dict) -> ToolResult:
    """
    Search for pages in Notion.
    """
    if not is_notion_configured():
        return ToolResult(
            success=False,
            error="Notion is not configured. Set NOTION_TOKEN in .env"
        )

    query = params.get("query", "")
    max_results = params.get("max_results", 10)

    try:
        data = {
            "query": query,
            "page_size": max_results,
            "filter": {"property": "object", "value": "page"}
        }

        result = await _make_notion_request("POST", "/search", data)

        if result is None:
            return ToolResult(success=False, error="Failed to search pages")

        pages = []
        for item in result.get("results", [])[:max_results]:
            # Extract title from properties
            title_prop = item.get("properties", {}).get("title", {})
            title_items = title_prop.get("title", [])
            title = title_items[0].get("plain_text", "Untitled") if title_items else "Untitled"

            pages.append({
                "id": item.get("id"),
                "title": title,
                "url": item.get("url"),
                "created_time": item.get("created_time"),
                "last_edited": item.get("last_edited_time")
            })

        return ToolResult(success=True, data={
            "count": len(pages),
            "pages": pages
        })

    except Exception as e:
        logger.error(f"Error searching Notion pages: {query}", e)
        return ToolResult(success=False, error=str(e))


search_pages_tool = MCPTool(
    name="notion_search_pages",
    description="Search for pages in Notion. Use this to find existing documentation or notes.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 10
            }
        },
        "required": []
    },
    execute=_search_pages
)


# ==============================================================================
# Register Notion tools
# ==============================================================================

def register_notion_tools():
    """Register all Notion tools with the registry."""
    tool_registry.register(create_page_tool)
    tool_registry.register(append_to_page_tool)
    tool_registry.register(search_pages_tool)
    logger.info("Registered Notion tools")


# Auto-register on import
register_notion_tools()

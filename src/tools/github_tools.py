"""
GitHub MCP Tools
================

Tools for interacting with GitHub: creating issues, searching code.

These tools allow the agent to:
- Create issues from Slack discussions
- Search code across repositories
- List repository information

GitHub API Notes:
- Uses httpx for async HTTP requests
- Requires a Personal Access Token with 'repo' scope
- Rate limits: 5000 requests/hour for authenticated requests

MCP Server Pattern:
    This module follows the MCP (Model Context Protocol) pattern:
    - Tools are self-contained functions
    - Each tool has a clear schema
    - Results are standardized via ToolResult
"""

import httpx

from src.tools import MCPTool, ToolResult, tool_registry
from src.utils.config import get_config, is_github_configured
from src.utils.logger import Logger

logger = Logger("GitHubTools")

# GitHub API base URL
GITHUB_API = "https://api.github.com"


async def _make_github_request(
    method: str,
    endpoint: str,
    data: dict | None = None
) -> dict | None:
    """
    Make an authenticated request to the GitHub API.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint (e.g., /repos/owner/repo/issues)
        data: Request body for POST/PATCH

    Returns:
        Response JSON or None if failed
    """
    config = get_config()

    if not config.github.token:
        return None

    headers = {
        "Authorization": f"Bearer {config.github.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    url = f"{GITHUB_API}{endpoint}"

    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=data)
        else:
            response = await client.request(method, url, headers=headers, json=data)

        if response.status_code >= 400:
            logger.error(f"GitHub API error: {response.status_code} - {response.text}")
            return None

        return response.json()


# ==============================================================================
# Tool: Create Issue
# ==============================================================================

async def _create_issue(params: dict) -> ToolResult:
    """
    Create a GitHub issue.

    Creates an issue in the specified repository with title, body, and labels.
    """
    if not is_github_configured():
        return ToolResult(
            success=False,
            error="GitHub is not configured. Set GITHUB_TOKEN in .env"
        )

    repo = params.get("repo")
    title = params.get("title")
    body = params.get("body", "")
    labels = params.get("labels", [])

    if not repo or not title:
        return ToolResult(success=False, error="Repository and title are required")

    # Use default repo if not fully qualified
    if "/" not in repo:
        config = get_config()
        if config.github.default_repo:
            repo = config.github.default_repo
        else:
            return ToolResult(
                success=False,
                error="Repo must be in 'owner/repo' format or set GITHUB_DEFAULT_REPO"
            )

    try:
        endpoint = f"/repos/{repo}/issues"
        data = {
            "title": title,
            "body": body
        }
        if labels:
            data["labels"] = labels

        result = await _make_github_request("POST", endpoint, data)

        if result is None:
            return ToolResult(success=False, error="Failed to create issue")

        return ToolResult(success=True, data={
            "issue_number": result.get("number"),
            "url": result.get("html_url"),
            "title": result.get("title"),
            "state": result.get("state")
        })

    except Exception as e:
        logger.error(f"Error creating issue in {repo}", e)
        return ToolResult(success=False, error=str(e))


create_issue_tool = MCPTool(
    name="github_create_issue",
    description="Create a new issue in a GitHub repository. Use this to track bugs or tasks found in Slack discussions.",
    parameters={
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository in 'owner/repo' format (or just 'repo' if default is set)"
            },
            "title": {
                "type": "string",
                "description": "Issue title"
            },
            "body": {
                "type": "string",
                "description": "Issue description/body (markdown supported)"
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Labels to apply to the issue"
            }
        },
        "required": ["repo", "title"]
    },
    execute=_create_issue
)


# ==============================================================================
# Tool: Search Code
# ==============================================================================

async def _search_code(params: dict) -> ToolResult:
    """
    Search for code across GitHub repositories.

    Uses GitHub's code search API to find code matching a query.
    """
    if not is_github_configured():
        return ToolResult(
            success=False,
            error="GitHub is not configured. Set GITHUB_TOKEN in .env"
        )

    query = params.get("query")
    repo = params.get("repo")
    language = params.get("language")
    max_results = params.get("max_results", 10)

    if not query:
        return ToolResult(success=False, error="Query is required")

    try:
        # Build the search query
        search_query = query
        if repo:
            search_query += f" repo:{repo}"
        if language:
            search_query += f" language:{language}"

        endpoint = f"/search/code?q={search_query}&per_page={max_results}"
        result = await _make_github_request("GET", endpoint)

        if result is None:
            return ToolResult(success=False, error="Failed to search code")

        items = result.get("items", [])
        formatted = []

        for item in items[:max_results]:
            formatted.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "repository": item.get("repository", {}).get("full_name"),
                "url": item.get("html_url"),
                "score": item.get("score")
            })

        return ToolResult(success=True, data={
            "total_count": result.get("total_count", 0),
            "results": formatted
        })

    except Exception as e:
        logger.error(f"Error searching code: {query}", e)
        return ToolResult(success=False, error=str(e))


search_code_tool = MCPTool(
    name="github_search_code",
    description="Search for code across GitHub repositories. Use this to find implementations or references.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (code, function name, etc.)"
            },
            "repo": {
                "type": "string",
                "description": "Limit search to a specific repo (owner/repo format)"
            },
            "language": {
                "type": "string",
                "description": "Filter by programming language"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 10)",
                "default": 10
            }
        },
        "required": ["query"]
    },
    execute=_search_code
)


# ==============================================================================
# Tool: List Repositories
# ==============================================================================

async def _list_repos(params: dict) -> ToolResult:
    """
    List repositories for a user or organization.
    """
    if not is_github_configured():
        return ToolResult(
            success=False,
            error="GitHub is not configured. Set GITHUB_TOKEN in .env"
        )

    owner = params.get("owner")
    repo_type = params.get("type", "all")  # all, owner, member
    max_results = params.get("max_results", 10)

    try:
        if owner:
            endpoint = f"/users/{owner}/repos?type={repo_type}&per_page={max_results}"
        else:
            # List authenticated user's repos
            endpoint = f"/user/repos?type={repo_type}&per_page={max_results}"

        result = await _make_github_request("GET", endpoint)

        if result is None:
            return ToolResult(success=False, error="Failed to list repositories")

        repos = []
        for repo in result[:max_results]:
            repos.append({
                "name": repo.get("full_name"),
                "description": repo.get("description"),
                "url": repo.get("html_url"),
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count"),
                "is_private": repo.get("private")
            })

        return ToolResult(success=True, data={
            "count": len(repos),
            "repositories": repos
        })

    except Exception as e:
        logger.error(f"Error listing repositories", e)
        return ToolResult(success=False, error=str(e))


list_repos_tool = MCPTool(
    name="github_list_repos",
    description="List GitHub repositories for a user or organization.",
    parameters={
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "GitHub username or org (omit for authenticated user's repos)"
            },
            "type": {
                "type": "string",
                "enum": ["all", "owner", "member"],
                "description": "Type of repos to list",
                "default": "all"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 10
            }
        },
        "required": []
    },
    execute=_list_repos
)


# ==============================================================================
# Register GitHub tools
# ==============================================================================

def register_github_tools():
    """Register all GitHub tools with the registry."""
    tool_registry.register(create_issue_tool)
    tool_registry.register(search_code_tool)
    tool_registry.register(list_repos_tool)
    logger.info("Registered GitHub tools")


# Auto-register on import
register_github_tools()

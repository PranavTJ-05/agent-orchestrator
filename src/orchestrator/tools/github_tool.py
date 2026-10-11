from __future__ import annotations

import json
import os
from typing import Any

import httpx

from ..core.tool import Tool


class GitHubTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="github",
            description="Interact with GitHub repositories. Use this to list repos, read files, create issues, and manage pull requests.",
        )

    async def execute(
        self,
        action: str,
        repo: str = "",
        path: str = "",
        content: str = "",
        title: str = "",
        body: str = "",
        query: str = "",
    ) -> str:
        """Execute a GitHub API operation.

        Args:
            action: One of: list_repos, read_file, write_file, search_code, create_issue, create_pr, list_issues
            repo: Repository name in format "owner/repo" (e.g. "user/my-repo")
            path: File path within the repository
            content: File content for write_file, or issue/PR body
            title: Title for create_issue or create_pr
            body: Body for create_pr
            query: Search query for search_code
        """
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return "Error: GITHUB_TOKEN environment variable not set. Set it to use the GitHub tool."

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                if action == "list_repos":
                    resp = await client.get("https://api.github.com/user/repos?per_page=10&sort=updated")
                    resp.raise_for_status()
                    repos = resp.json()
                    if not repos:
                        return "No repositories found."
                    lines = ["Your repositories:"]
                    for r in repos:
                        lines.append(f"  - {r['full_name']}: {r.get('description', 'No description')}")
                    return "\n".join(lines)

                elif action == "read_file":
                    if not repo or not path:
                        return "Error: Both 'repo' (owner/repo) and 'path' are required."
                    url = f"https://api.github.com/repos/{repo}/contents/{path}"
                    resp = await client.get(url)
                    if resp.status_code == 404:
                        return f"Error: File not found at {repo}/{path}"
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, list):
                        items = [f"  {i['name']}/" if i['type'] == 'dir' else f"  {i['name']}" for i in data]
                        return f"Contents of {repo}/{path}:\n" + "\n".join(items)
                    import base64
                    decoded = base64.b64decode(data["content"]).decode("utf-8")
                    return f"File: {repo}/{path}\n\n{decoded}"

                elif action == "write_file":
                    if not repo or not path:
                        return "Error: Both 'repo' (owner/repo) and 'path' are required."
                    # First check if file exists to get the SHA
                    url = f"https://api.github.com/repos/{repo}/contents/{path}"
                    sha = None
                    check_resp = await client.get(url)
                    if check_resp.status_code == 200:
                        sha = check_resp.json().get("sha")

                    import base64
                    payload = {
                        "message": f"Update {path}",
                        "content": base64.b64encode(content.encode()).decode(),
                    }
                    if sha:
                        payload["sha"] = sha
                    else:
                        payload["message"] = f"Create {path}"

                    resp = await client.put(url, json=payload)
                    if resp.status_code in (200, 201):
                        return f"Successfully wrote to {repo}/{path}"
                    return f"Error: {resp.status_code} - {resp.text}"

                elif action == "search_code":
                    if not query:
                        return "Error: 'query' is required for search_code."
                    resp = await client.get(f"https://api.github.com/search/code?q={query}&per_page=5")
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("items", [])
                    if not items:
                        return f"No results found for query: {query}"
                    results = [f"Search results for '{query}':"]
                    for item in items[:5]:
                        results.append(f"  - {item['repository']['full_name']}/{item['path']}")
                    return "\n".join(results)

                elif action == "create_issue":
                    if not repo or not title:
                        return "Error: Both 'repo' (owner/repo) and 'title' are required."
                    url = f"https://api.github.com/repos/{repo}/issues"
                    payload = {"title": title, "body": body or ""}
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 201:
                        data = resp.json()
                        return f"Issue created: {data['html_url']}"
                    return f"Error: {resp.status_code} - {resp.text}"

                elif action == "create_pr":
                    if not repo or not title:
                        return "Error: Both 'repo' (owner/repo) and 'title' are required."
                    url = f"https://api.github.com/repos/{repo}/pulls"
                    payload = {
                        "title": title,
                        "body": body or "",
                        "head": content or "main",  # Use 'content' as head branch
                        "base": "main",
                    }
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 201:
                        data = resp.json()
                        return f"PR created: {data['html_url']}"
                    return f"Error: {resp.status_code} - {resp.text}"

                elif action == "list_issues":
                    if not repo:
                        return "Error: 'repo' (owner/repo) is required."
                    url = f"https://api.github.com/repos/{repo}/issues"
                    resp = await client.get(url)
                    resp.raise_for_status()
                    issues = resp.json()
                    if not issues:
                        return f"No issues found for {repo}."
                    lines = [f"Issues for {repo}:"]
                    for issue in issues[:10]:
                        lines.append(f"  #{issue['number']} {'✅' if issue['state'] == 'open' else '❌'} {issue['title']}")
                    return "\n".join(lines)

                else:
                    return f"Error: Unknown action '{action}'. Supported: list_repos, read_file, write_file, search_code, create_issue, create_pr, list_issues"

        except Exception as e:
            return f"Error executing GitHub action '{action}': {str(e)}"

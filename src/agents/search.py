from duckduckgo_search import DDGS

from .base import BaseAgent


class SearchAgent(BaseAgent):
    name = "web_search"
    description = (
        "Search the web for current information: news, weather, prices, facts. "
        "Use for anything requiring real-time data beyond your knowledge cutoff."
    )

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def execute(self, action: str, params: dict) -> dict:
        if action == "web_search":
            return self._handle_web_search(params)
        if action == "web_fetch":
            return self._handle_web_fetch(params)
        return {"error": f"Unknown action: {action}"}

    def _handle_web_search(self, p: dict) -> dict:
        query = p.get("query", "")
        if not query:
            return {"error": "query is required"}

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            return {
                "status": "ok",
                "count": len(results),
                "results": [
                    {"title": r["title"], "url": r["href"], "snippet": r["body"]}
                    for r in results
                ],
            }
        except Exception as e:
            return {"error": f"Search failed: {e}"}

    def _handle_web_fetch(self, p: dict) -> dict:
        url = p.get("url", "")
        if not url:
            return {"error": "url is required"}

        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8", errors="ignore")[:4000]
            return {"status": "ok", "url": url, "text": text}
        except Exception as e:
            return {"error": f"Fetch failed: {e}"}

    def get_tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["web_search", "web_fetch"],
                            "description": "Action: web_search for results, web_fetch to read full page",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g. 'weather Lisbon today', 'latest Bitcoin price')",
                        },
                        "url": {
                            "type": "string",
                            "description": "URL to fetch (for web_fetch action)",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

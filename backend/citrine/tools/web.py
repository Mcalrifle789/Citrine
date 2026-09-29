"""Searching the web, as a tool.

`fetch_url` answers "what is at this URL?". It cannot answer "what is the
URL?" - which is what most internet questions actually are. `web_search` is the
other half.

The backend is DuckDuckGo's HTML endpoint, chosen because it needs no API key,
no account, and no quota: the tool works the moment Citrine is installed, and
the search-setup slice (/searchsetup with Perplexity, Brave, and friends) can
replace it later without changing the tool's shape. The endpoint is a module
constant rather than a literal inside the function so tests can point it at a
local server instead of the internet.

Scraping HTML with the stdlib parser is deliberately unglamorous. The markup
being parsed is served by a search engine to browsers without JavaScript, so
it is stable enough to parse, and the failure mode of a layout change is a
result saying so - not a stack trace in the chat.
"""

from __future__ import annotations

import html.parser
import urllib.parse
import urllib.request

from citrine.tools.base import ToolContext, ToolResult, truncate

# Overridable so tests can serve canned result pages from loopback.
DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (compatible; Citrine/0.1; +https://github.com/Mcalrifle789/Citrine)"
TIMEOUT_S = 20
MAX_RESULTS = 8
MAX_SNIPPET_CHARS = 300


class _ResultsParser(html.parser.HTMLParser):
    """Collects result links and snippets from the HTML results page.

    The page marks results with stable classes: `result__a` for the title
    link, `result__snippet` for the summary. Anything else is ignored.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._in_title = False
        self._in_snippet = False
        self._pending: dict[str, str] = {}
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        css = attributes.get("class", "")
        if tag == "a" and "result__a" in css:
            self._in_title = True
            self._pending = {"url": self._clean_url(attributes.get("href", ""))}
            self._text = []
        elif tag == "a" and "result__snippet" in css:
            self._in_snippet = True
            self._text = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title:
            self._in_title = False
            title = " ".join("".join(self._text).split())
            if title:
                self._pending["title"] = title
                self.results.append(self._pending)
            self._pending = {}
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            if self.results:
                snippet = " ".join("".join(self._text).split())[:MAX_SNIPPET_CHARS]
                self.results[-1]["snippet"] = snippet

    def handle_data(self, data):
        if self._in_title or self._in_snippet:
            self._text.append(data)

    @staticmethod
    def _clean_url(href: str) -> str:
        """DuckDuckGo wraps outbound links in /l/?uddg=<encoded>; unwrap it."""
        if not href:
            return ""
        if href.startswith("//"):
            href = "https:" + href
        parsed = urllib.parse.urlparse(href)
        if parsed.path.startswith("/l/"):
            query = urllib.parse.parse_qs(parsed.query)
            return query.get("uddg", [""])[0]
        return href


def web_search(
    query: str,
    ctx: ToolContext,
    *,
    max_results: int = MAX_RESULTS,
    endpoint: str | None = None,
) -> ToolResult:
    """Search the web and return titles, URLs and snippets."""
    if not ctx.allow_network:
        return ToolResult.failure("network access is disabled (tools.allow_network is false)")

    # Resolved at call time, not as a default argument: tests point the module
    # constant at a local server, and a default bound at definition time would
    # ignore that.
    base = endpoint or DUCKDUCKGO_URL
    text = (query or "").strip()
    if not text:
        return ToolResult.failure("No search query given.")

    url = base + "?" + urllib.parse.urlencode({"q": text})
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            page = response.read(512 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return ToolResult.failure(f"Search failed with HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        return ToolResult.failure(f"Search failed: {exc.reason}")
    except OSError as exc:
        return ToolResult.failure(f"Search failed: {exc}")

    parser = _ResultsParser()
    parser.feed(page)

    if not parser.results:
        return ToolResult.success(
            f'No results for "{text}". The search engine may have changed its '
            "markup, or the query may be too narrow."
        )

    lines = [f'Search results for "{text}":', ""]
    for index, result in enumerate(parser.results[: max(1, max_results)], start=1):
        title = result.get("title", "(untitled)")
        link = result.get("url", "")
        snippet = result.get("snippet", "")
        lines.append(f"{index}. {title}")
        if link:
            lines.append(f"   {link}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")

    body = "\n".join(lines).rstrip()
    return ToolResult.success(
        truncate(
            body + "\nUse fetch_url on any of these links to read the full page.",
            ctx.max_output_chars,
            note="search results truncated",
        )
    )

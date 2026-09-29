"""web_search against a canned results page.

The search endpoint is a module constant, so these tests point it at a local
server serving a snapshot of the real markup shape instead of the internet -
deterministic, free, and unable to fail because someone else's site is down.
"""

from __future__ import annotations

import http.server
import threading
from pathlib import Path

import pytest

from citrine.tools import ToolContext, execute
from citrine.tools import web


RESULT_PAGE = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fguide">The Best Guide</a>
  <a class="result__snippet">A guide about <b>things</b> and stuff.</a>
</div>
<div class="result">
  <a class="result__a" href="https://direct.example.org/page">Direct Link Result</a>
  <a class="result__snippet">Snippet two.</a>
</div>
</body></html>
"""


@pytest.fixture()
def search_server(monkeypatch):
    """Serve the canned page and point the tool at it."""

    class Handler(http.server.BaseHTTPRequestHandler):
        seen_query = ""

        def do_GET(self):  # noqa: N802 - http.server's interface
            Handler.seen_query = self.path
            body = RESULT_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(web, "DUCKDUCKGO_URL", f"http://127.0.0.1:{server.server_address[1]}/html/")
    try:
        yield Handler
    finally:
        server.shutdown()
        server.server_close()


def ctx_for(tmp_path: Path) -> ToolContext:
    return ToolContext(root=tmp_path, timeout_s=15)


class TestWebSearch:
    def test_returns_results_with_unwrapped_urls(self, tmp_path, search_server):
        result = execute("web_search", {"query": "things"}, ctx_for(tmp_path))

        assert result.ok
        assert "The Best Guide" in result.content
        # The /l/?uddg= wrapper was unwrapped to the real destination.
        assert "https://example.com/guide" in result.content
        assert "Direct Link Result" in result.content
        assert "https://direct.example.org/page" in result.content
        assert "A guide about things and stuff." in result.content

    def test_sends_the_query(self, tmp_path, search_server):
        execute("web_search", {"query": "citrine agent"}, ctx_for(tmp_path))
        assert "q=citrine+agent" in search_server.seen_query

    def test_empty_query_is_refused(self, tmp_path, search_server):
        result = execute("web_search", {"query": "  "}, ctx_for(tmp_path))
        assert not result.ok
        assert "No search query" in result.content

    def test_disabled_network_refuses(self, tmp_path, search_server):
        ctx = ctx_for(tmp_path)
        ctx.allow_network = False
        result = execute("web_search", {"query": "x"}, ctx)
        assert not result.ok
        assert "network access is off" in result.content

    def test_no_results_says_so_instead_of_failing(self, tmp_path, monkeypatch):
        class Empty(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = b"<html><body></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Empty)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setattr(web, "DUCKDUCKGO_URL", f"http://127.0.0.1:{server.server_address[1]}/")
        try:
            result = execute("web_search", {"query": "obscure"}, ctx_for(tmp_path))
            assert result.ok
            assert "No results" in result.content
        finally:
            server.shutdown()
            server.server_close()

    def test_http_errors_are_readable(self, tmp_path, monkeypatch):
        class Down(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_error(503)

            def log_message(self, *args):
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Down)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setattr(web, "DUCKDUCKGO_URL", f"http://127.0.0.1:{server.server_address[1]}/")
        try:
            result = execute("web_search", {"query": "x"}, ctx_for(tmp_path))
            assert not result.ok
            assert "503" in result.content
        finally:
            server.shutdown()
            server.server_close()

    def test_is_offered_to_the_model_when_network_is_on(self, tmp_path):
        from citrine.tools import specs

        names = {spec["function"]["name"] for spec in specs(ToolContext(root=tmp_path))}
        assert "web_search" in names

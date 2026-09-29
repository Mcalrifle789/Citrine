"""The agent's tools: files, terminal, git, network.

These run against the real thing - real files, real subprocesses, real git in
a temporary directory - because the behaviour under test *is* the interaction
with the machine. A mocked subprocess would assert that the right command was
composed, which is the part that was never in doubt.

Nothing here touches the public internet: the network tests serve their own
responses from a loopback HTTP server, so they pass on a machine with no
connection and cannot fail because someone else's site is down.
"""

from __future__ import annotations

import base64
import http.server
import io
import json
import subprocess
import threading
import zipfile
from pathlib import Path

import pytest

from citrine.tools import ToolContext, magic
from citrine.tools import execute, specs
from citrine.tools.base import ToolError
from citrine.tools.files import list_dir, read_file, write_file
from citrine.tools.network import fetch_url
from citrine.tools.registry import Tool
from citrine.tools.terminal import blocked_reason, run_command


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(root=tmp_path, timeout_s=30, max_output_chars=5000)


# ------------------------------------------------------------------- files ---


class TestReadFile:
    def test_reads_text_with_line_numbers(self, ctx):
        (ctx.root / "app.py").write_text("alpha\nbeta\n", encoding="utf-8")
        result = read_file("app.py", ctx)
        assert result.ok
        assert "1\talpha" in result.content
        assert "2\tbeta" in result.content

    def test_pages_through_a_large_file(self, ctx):
        (ctx.root / "big.txt").write_text(
            "\n".join(f"line {index}" for index in range(1, 101)), encoding="utf-8"
        )
        result = read_file("big.txt", ctx, start_line=50, max_lines=5)
        assert "50\tline 50" in result.content
        assert "55\tline 55" not in result.content
        assert "more lines" in result.content

    def test_describes_a_binary_file_instead_of_refusing(self, ctx):
        """The regression this whole module exists for."""
        payload = b"\x89PNG\r\n\x1a\n" + bytes(range(64))
        (ctx.root / "logo.png").write_bytes(payload)

        result = read_file("logo.png", ctx)

        assert result.ok
        assert "PNG image" in result.content
        # The bytes themselves are handed over, base64-encoded.
        assert base64.b64encode(payload[:16]).decode().rstrip("=")[:12] in result.content

    def test_extracts_text_from_a_docx_container(self, ctx):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                "<w:p><w:r><w:t>Hello from Word</w:t></w:r></w:p>",
            )
        (ctx.root / "report.docx").write_bytes(buffer.getvalue())

        result = read_file("report.docx", ctx)

        assert "Hello from Word" in result.content
        assert "extracted" in result.content

    def test_reports_a_missing_file(self, ctx):
        result = read_file("nope.txt", ctx)
        assert not result.ok
        assert "No such file" in result.content

    def test_refuses_to_read_a_directory(self, ctx):
        (ctx.root / "src").mkdir()
        result = read_file("src", ctx)
        assert not result.ok
        assert "directory" in result.content

    def test_refuses_a_path_outside_the_workspace(self, ctx):
        with pytest.raises(ToolError, match="outside the workspace root"):
            read_file("../escape.txt", ctx)

    def test_allows_outside_paths_when_opted_in(self, tmp_path):
        outside = tmp_path.parent / "outside-allowed.txt"
        outside.write_text("visible", encoding="utf-8")
        root = tmp_path / "root"
        root.mkdir()
        permissive = ToolContext(root=root, allow_outside_workspace=True)

        try:
            result = read_file(str(outside), permissive)
            assert result.ok
            assert "visible" in result.content
        finally:
            outside.unlink(missing_ok=True)

    def test_refuses_when_file_access_is_switched_off(self, ctx):
        # Called directly the guard raises; through the registry it becomes a
        # result (see test_the_registry_says_why_a_tool_is_unavailable).
        ctx.allow_files = False
        with pytest.raises(ToolError, match="file access is disabled"):
            read_file("anything.txt", ctx)

    def test_the_registry_says_why_a_tool_is_unavailable(self, ctx):
        """A disabled tool is reported by the dispatcher, not run."""
        ctx.allow_files = False
        result = execute("read_file", {"path": "anything.txt"}, ctx)
        assert not result.ok
        assert "not available" in result.content
        assert "tools.allow_files" in result.content


class TestWriteFile:
    def test_writes_and_creates_parents(self, ctx):
        result = write_file("deep/nested/note.md", "hello\n", ctx)
        assert result.ok
        assert (ctx.root / "deep" / "nested" / "note.md").read_text(encoding="utf-8") == "hello\n"

    def test_overwrites_by_default(self, ctx):
        write_file("note.md", "first", ctx)
        write_file("note.md", "second", ctx)
        assert (ctx.root / "note.md").read_text(encoding="utf-8") == "second"

    def test_appends_when_asked(self, ctx):
        write_file("note.md", "first\n", ctx)
        write_file("note.md", "second\n", ctx, mode="append")
        assert (ctx.root / "note.md").read_text(encoding="utf-8") == "first\nsecond\n"

    def test_refuses_when_writes_are_disabled(self, ctx):
        ctx.allow_write = False
        result = write_file("note.md", "x", ctx)
        assert not result.ok
        assert "writing files is disabled" in result.content


class TestListDir:
    def test_lists_files_and_directories(self, ctx):
        (ctx.root / "src").mkdir()
        (ctx.root / "src" / "main.py").write_text("x", encoding="utf-8")
        (ctx.root / "readme.md").write_text("x", encoding="utf-8")

        result = list_dir(".", ctx)

        assert "src/" in result.content
        assert "readme.md" in result.content

    def test_recurses_to_the_requested_depth(self, ctx):
        (ctx.root / "a" / "b").mkdir(parents=True)
        (ctx.root / "a" / "b" / "deep.txt").write_text("x", encoding="utf-8")

        shallow = list_dir(".", ctx, depth=1)
        deep = list_dir(".", ctx, depth=3)

        assert "deep.txt" not in shallow.content
        assert "deep.txt" in deep.content

    def test_skips_noise_directories(self, ctx):
        (ctx.root / "node_modules").mkdir()
        (ctx.root / "node_modules" / "junk.js").write_text("x", encoding="utf-8")

        result = list_dir(".", ctx, depth=2)

        assert "junk.js" not in result.content


# ---------------------------------------------------------------- terminal ---


class TestRunCommand:
    def test_captures_stdout_and_exit_code(self, ctx):
        result = run_command("python -c \"print('hi')\"", ctx)
        assert result.ok
        assert "hi" in result.content
        assert "[exit code: 0]" in result.content

    def test_reports_a_failing_exit_code(self, ctx):
        result = run_command("python -c \"import sys; sys.exit(3)\"", ctx)
        assert "[exit code: 3]" in result.content

    def test_runs_in_the_workspace_root(self, ctx):
        (ctx.root / "marker.txt").write_text("x", encoding="utf-8")
        result = run_command("python -c \"import os; print(sorted(os.listdir('.')))\"", ctx)
        assert "marker.txt" in result.content

    def test_honours_an_explicit_cwd(self, ctx):
        (ctx.root / "sub").mkdir()
        (ctx.root / "sub" / "inner.txt").write_text("x", encoding="utf-8")
        result = run_command("python -c \"import os; print(os.listdir('.'))\"", ctx, cwd="sub")
        assert "inner.txt" in result.content

    def test_times_out_rather_than_hanging(self, ctx):
        result = run_command(
            "python -c \"import time; time.sleep(30)\"", ctx, timeout_s=2
        )
        assert not result.ok
        assert "timed out" in result.content

    def test_caps_the_output(self, ctx):
        ctx.max_output_chars = 200
        result = run_command(
            "python -c \"print('y' * 5000)\"", ctx
        )
        assert len(result.content) < 1000
        assert "truncated" in result.content

    def test_refuses_destructive_commands(self, ctx):
        result = run_command("rm -rf /", ctx)
        assert not result.ok
        assert "destructive list" in result.content

    def test_refuses_git_reset_hard_through_the_shell_too(self, ctx):
        result = run_command("git reset --hard HEAD~5", ctx)
        assert not result.ok
        assert "discarding uncommitted work" in result.content

    def test_allows_destructive_when_opted_in(self, ctx):
        ctx.allow_destructive = True
        # Still refused by the shell itself, but no longer by our guard: the
        # point is that the policy decision moved to the user.
        result = run_command("git reset --hard", ctx)
        assert "destructive list" not in result.content

    def test_respects_the_terminal_switch(self, ctx):
        ctx.allow_terminal = False
        result = run_command("echo hi", ctx)
        assert not result.ok
        assert "terminal access is disabled" in result.content

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "git push --force origin main",
            "git clean -xfd",
            "shutdown /s /t 0",
            "mkfs.ext4 /dev/sda1",
            "reg delete HKLM\\Software /f",
        ],
    )
    def test_blocked_reason_matches_known_dangers(self, command):
        assert blocked_reason(command) is not None

    @pytest.mark.parametrize("command", ["ls -la", "git status", "npm test", "python app.py"])
    def test_blocked_reason_ignores_ordinary_commands(self, command):
        assert blocked_reason(command) is None


# --------------------------------------------------------------------- git ---


def _git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "user@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "User"], cwd=path, check=True)


class TestGit:
    def test_status_reports_untracked_files(self, ctx):
        _git_repo(ctx.root)
        (ctx.root / "new.txt").write_text("x", encoding="utf-8")

        result = execute("git", {"args": ["status", "--short"]}, ctx)

        assert result.ok
        assert "new.txt" in result.content

    def test_commit_credits_citrine_as_co_author(self, ctx):
        _git_repo(ctx.root)
        (ctx.root / "new.txt").write_text("x", encoding="utf-8")
        execute("git", {"args": ["add", "."]}, ctx)

        result = execute("git", {"args": ["commit", "-m", "add new file"]}, ctx)

        assert result.ok
        log = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"], cwd=ctx.root, capture_output=True, text=True
        ).stdout
        assert "add new file" in log
        assert "Co-Authored-By:" in log
        assert "citrine" in log.lower()

    def test_commit_does_not_stack_duplicate_trailers(self, ctx):
        _git_repo(ctx.root)
        (ctx.root / "one.txt").write_text("x", encoding="utf-8")
        execute("git", {"args": ["add", "."]}, ctx)
        execute("git", {"args": ["commit", "-m", "first", "-m", "Co-Authored-By: Citrine Agent <citrine-agent@users.noreply.github.com>"]}, ctx)

        log = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"], cwd=ctx.root, capture_output=True, text=True
        ).stdout
        assert log.lower().count("co-authored-by:") == 1

    def test_refuses_a_forced_push(self, ctx):
        _git_repo(ctx.root)
        result = execute("git", {"args": ["push", "--force", "origin", "main"]}, ctx)
        assert not result.ok
        assert "rewriting published history" in result.content

    def test_accepts_a_command_string(self, ctx):
        _git_repo(ctx.root)
        result = execute("git", {"args": "status --short"}, ctx)
        assert result.ok

    def test_respects_the_git_switch(self, ctx):
        ctx.allow_git = False
        result = execute("git", {"args": ["status"]}, ctx)
        assert not result.ok
        assert "git access is off" in result.content


# ----------------------------------------------------------------- network ---


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves whatever the test asked for, and records the request."""

    payload = b"{}"
    content_type = "application/json"
    status = 200
    requests: list[tuple[str, str]] = []

    def do_GET(self):  # noqa: N802 - http.server's interface
        type(self).requests.append(("GET", self.path))
        self._respond()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        type(self).requests.append(("POST", body))
        self._respond()

    def _respond(self):
        self.send_response(self.status)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args):  # silence the test output
        return


@pytest.fixture()
def http_server():
    _Handler.requests = []
    _Handler.payload = b"{}"
    _Handler.content_type = "application/json"
    _Handler.status = 200
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()


class TestFetchUrl:
    def test_fetches_and_pretty_prints_json(self, ctx, http_server):
        _Handler.payload = json.dumps({"b": 2, "a": 1}).encode()

        result = fetch_url(http_server, ctx)

        assert result.ok
        assert '"a": 1' in result.content
        # Pretty-printed means newlines, not one minified line.
        assert "\n" in result.content

    def test_posts_a_body(self, ctx, http_server):
        result = fetch_url(
            http_server, ctx, method="POST", body='{"hello": "world"}'
        )
        assert result.ok
        assert ("POST", '{"hello": "world"}') in _Handler.requests

    def test_reports_an_http_error_with_the_body(self, ctx, http_server):
        _Handler.status = 404
        _Handler.payload = b"nope"

        result = fetch_url(http_server, ctx)

        assert not result.ok
        assert "404" in result.content
        assert "nope" in result.content

    def test_describes_a_binary_response(self, ctx, http_server):
        _Handler.content_type = "image/png"
        _Handler.payload = b"\x89PNG\r\n\x1a\n" + bytes(32)

        result = fetch_url(http_server, ctx)

        assert result.ok
        assert "PNG image" in result.content

    def test_refuses_non_http_schemes(self, ctx):
        result = fetch_url("file:///etc/passwd", ctx)
        assert not result.ok
        assert "only http and https" in result.content

    def test_respects_the_network_switch(self, ctx, http_server):
        ctx.allow_network = False
        result = fetch_url(http_server, ctx)
        assert not result.ok
        assert "network access is disabled" in result.content


# ---------------------------------------------------------------- registry ---


class TestRegistry:
    def test_every_tool_has_a_well_formed_schema(self):
        for spec in specs(ToolContext(root=Path.cwd())):
            function = spec["function"]
            assert spec["type"] == "function"
            assert function["name"]
            assert function["description"]
            assert function["parameters"]["type"] == "object"

    def test_specs_shrink_with_the_policy(self, ctx):
        ctx.allow_git = False
        ctx.allow_network = False
        names = {spec["function"]["name"] for spec in specs(ctx)}
        assert "read_file" in names
        assert "git" not in names
        assert "fetch_url" not in names

    def test_unknown_tool_names_the_alternatives(self, ctx):
        result = execute("obliterate", {}, ctx)
        assert not result.ok
        assert "Unknown tool" in result.content
        assert "read_file" in result.content

    def test_malformed_json_arguments_are_reported(self, ctx):
        result = execute("read_file", "{not json", ctx)
        assert not result.ok
        assert "Could not parse arguments" in result.content

    def test_wrong_arguments_list_the_expected_schema(self, ctx):
        result = execute("read_file", {"wrong": "key"}, ctx)
        assert not result.ok
        assert "Bad arguments" in result.content
        assert "path" in result.content

    def test_a_raising_tool_costs_one_call_not_the_turn(self, ctx, monkeypatch):
        from citrine.tools import registry

        def explode(**kwargs):
            raise RuntimeError("boom")

        monkeypatch.setitem(
            registry.TOOL_INDEX,
            "read_file",
            Tool(
                name="read_file",
                description="x",
                parameters={"type": "object", "properties": {}},
                category="files",
                run=explode,
                enabled=lambda context: True,
                disabled_reason="",
            ),
        )

        result = execute("read_file", {"path": "x"}, ctx)
        assert not result.ok
        assert "boom" in result.content


# ------------------------------------------------------------------- magic ---


class TestMagic:
    def test_identifies_common_formats(self):
        assert magic.sniff(b"\x89PNG\r\n\x1a\n" + b"\x00") == "PNG image"
        assert magic.sniff(b"%PDF-1.7") == "PDF document"
        assert magic.sniff(b"PK\x03\x04rest") == "ZIP-based file"
        assert magic.sniff(b"\x7fELF\x02\x01\x01") == "ELF binary"
        assert magic.sniff(b"not a known format") == "unknown binary"

    def test_decodes_text_and_recognises_binary(self):
        assert magic.decode_text(b"plain text") == "plain text"
        assert magic.decode_text(b"with\x00nul") is None

    def test_flags_images(self):
        assert magic.is_image("PNG image")
        assert not magic.is_image("PDF document")

    def test_describe_binary_includes_type_and_payload(self):
        description = magic.describe_binary(b"\x89PNG\r\n\x1a\n" + bytes(8))
        assert "PNG image" in description
        assert "base64" in description

    def test_data_uri_for_vision_requests(self):
        uri = magic.image_data_uri(b"\x89PNG", "image/png")
        assert uri.startswith("data:image/png;base64,")

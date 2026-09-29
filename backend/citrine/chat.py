"""Chat routing for configured Citrine agents.

This module is the agent loop. A turn is no longer one request: the model is
given the tool set from ``citrine.tools``, and while it keeps asking for tools
the loop keeps answering - running each call locally and feeding the result
back as a ``tool`` message - until it produces prose. That is what makes
Citrine able to run a command, read the output, read a binary file, check git,
or fetch a URL inside a conversation instead of telling the user it cannot.

Two things the loop has to get right:

* **Degrading on providers without tool support.** A provider that rejects the
  ``tools`` field (or the image content parts) should still answer the
  question. Both cases are detected from the provider's error and retried once
  without the offending part of the request, rather than surfacing a 400.
* **Bounded work.** Rounds are capped, and every tool call is executed through
  the registry, which converts any exception in a tool into a readable result.
  A misbehaving tool costs one call, not the conversation.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from citrine import tools
from citrine import history
from citrine.attachments import Attachment, build_prompt, image_parts
from citrine.catalog import provider_by_id
from citrine.config import CitrineConfig
from citrine.secrets_store import load_secret, secret_key
from citrine.tokens import estimate_tokens

# Sent as the system message. It states the environment (so the model does not
# have to probe for it) and, more importantly, tells the model that having
# tools means using them: the failure this replaces was an agent that answered
# "I cannot read binary files" while holding a tool that reads them.
SYSTEM_PROMPT = """You are Citrine, a local-first personal terminal agent running on the user's own machine.

You have tools. Use them.

- Read files with read_file, including binary files: images, PDFs, archives, \
Office documents and executables are described with their detected type, any \
text extractable from their container, and a base64 prefix of the raw bytes.
- Run commands with run_command. It is a real shell with the user's \
permissions, in the workspace root. Use it to build, test, inspect, and run \
things rather than asking the user to run them.
- Use git for repository work, and fetch_url for network requests.
- Use web_search to search the web when you need to find something online; \
then fetch_url the promising results to read them.
- Never claim you cannot read a file, run a command, or reach the network \
before you have tried the relevant tool. If a tool refuses, say exactly why.

This conversation's earlier messages are included below. Build on what you \
already found instead of re-reading files you have already seen.

Workspace root: {root}
Shell commands run in: {shell}
Git: {git}

Be concise and concrete. Prefer acting over describing what you would do."""


@dataclass(frozen=True)
class ToolStep:
    """One tool the agent ran, for logging and for the transcript."""

    name: str
    ok: bool
    summary: str


@dataclass(frozen=True)
class ChatResult:
    text: str
    tokens_used: int
    steps: tuple[ToolStep, ...] = ()


@dataclass
class _Turn:
    """Mutable accounting for one conversation turn."""

    tokens: int = 0
    steps: list[ToolStep] = field(default_factory=list)


def send_chat(
    message: str,
    config: CitrineConfig | None = None,
    attachments: list[Attachment] | None = None,
    workspace: str | None = None,
    transcript_key: str | None = None,
) -> ChatResult:
    cfg = config or CitrineConfig()
    files = attachments or []

    provider = cfg.active_provider()
    if provider is None:
        return _plain(
            message,
            "No model provider is configured yet.\n"
            "Run `citrine setup`, or use /provider after setup is wired into the UI.",
        )

    descriptor = provider_by_id(provider.id)
    if descriptor is None:
        return _plain(message, f"Unknown provider: {provider.id}")

    model = cfg.active_agent_config().model or provider.model or descriptor.default_model
    if not model:
        return _plain(message, f"{provider.label} is configured, but no model is selected. Use /model <name>.")

    api_key = _api_key(provider.id, descriptor.env_var)
    if not api_key:
        return _plain(message, f"{provider.label} has no stored API key. Run `citrine setup`.")

    if descriptor.kind != "openai":
        return _plain(
            message,
            f"{provider.label} is selected with model {model}, but this provider adapter "
            "is not implemented yet. OpenAI-compatible providers work in this slice.",
        )

    base_url = provider.base_url or descriptor.base_url
    if not base_url:
        return _plain(message, f"{provider.label} needs a base URL before Citrine can call it. Run `citrine setup`.")

    context = tools.build_context(cfg, workspace)
    tool_specs = tools.specs(context) if cfg.tools.enabled else []

    # One HTTP call, and the whole turn. Without the second bound a turn is
    # limited only by max_rounds * request_timeout, which is long enough that
    # the user reasonably concludes the agent has hung.
    request_timeout = max(30, int(cfg.request_timeout_s or 180))
    deadline = time.monotonic() + max(request_timeout, int(cfg.turn_budget_s or 600))

    turn = _Turn()
    # Past turns come from the history store, keyed by the same transcript key
    # the renderer uses for its scrollback: when the window goes blank, the
    # model's memory goes with it. The current user message is kept as a
    # reference rather than a fixed index, because the image fallback below
    # has to rewrite it wherever it sits in the list.
    prior = history.STORE.messages_for(transcript_key) if transcript_key else []
    user_message = {"role": "user", "content": _user_content(message, files)}
    messages = [
        {"role": "system", "content": _system_prompt(context)},
        *prior,
        user_message,
    ]

    max_rounds = max(1, int(cfg.tools.max_rounds)) if cfg.tools.enabled else 1
    url = base_url.rstrip("/") + "/chat/completions"
    allow_tools = bool(tool_specs)
    allow_images = _has_images(files)

    for round_index in range(max_rounds):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _out_of_time(turn, round_index)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
        }
        if allow_tools:
            payload["tools"] = tool_specs
            payload["tool_choice"] = "auto"

        timeout = min(request_timeout, max(5.0, remaining))
        data, error = _post(url, api_key, payload, provider.label, timeout)

        if error is not None and _rejects_images(error) and allow_images:
            # The model cannot take image parts. Re-send without them and tell
            # the user once that the files were described rather than seen.
            allow_images = False
            user_message["content"] = _user_content(message, files, images=False)
            data, error = _post(url, api_key, payload, provider.label, timeout)
            if error is not None:
                return _failed(error, turn)

        if error is not None and allow_tools and _rejects_tools(error):
            allow_tools = False
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            data, error = _post(url, api_key, payload, provider.label, timeout)

        if error is not None:
            return _failed(error, turn)

        turn.tokens += _usage_tokens(data)
        choice = _first_choice(data)
        if choice is None:
            return ChatResult(
                f"{provider.label} returned an unexpected response: {json.dumps(data)[:500]}",
                turn.tokens,
                tuple(turn.steps),
            )

        response_message = choice.get("message") or {}
        tool_calls = response_message.get("tool_calls") or []

        if not tool_calls:
            text = str(response_message.get("content") or "").strip()
            if not text:
                text = "(the model returned an empty response)"
            if turn.tokens == 0:
                turn.tokens = estimate_tokens(message) + estimate_tokens(text)
            # The exchange is stored as what was asked and what was concluded -
            # not the attachment-folded prompt or the tool traffic, which would
            # rent permanent context space for payload the next turn cannot use.
            if transcript_key:
                history.STORE.record_turn(transcript_key, message, text)
            return ChatResult(text, turn.tokens, tuple(turn.steps))

        messages.append(_assistant_message(response_message, tool_calls))
        for call in tool_calls:
            name, arguments = _call_parts(call)
            result = tools.execute(name, arguments, context)
            turn.steps.append(
                ToolStep(name=name or "unknown", ok=result.ok, summary=_summary(result.content))
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id") or ""),
                    "name": name or "tool",
                    "content": result.content,
                }
            )

    # Out of rounds with the model still calling tools: report what happened
    # rather than looping forever.
    ran = ", ".join(step.name for step in turn.steps) or "nothing"
    return ChatResult(
        f"I stopped after {max_rounds} rounds of tool calls without producing "
        f"a final answer. Tools used: {ran}.",
        turn.tokens or estimate_tokens(message),
        tuple(turn.steps),
    )


# ------------------------------------------------------------------ helpers ---


def _plain(message: str, text: str) -> ChatResult:
    return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))


def _failed(error: str, turn: _Turn) -> ChatResult:
    return ChatResult(error, turn.tokens, tuple(turn.steps))


def _system_prompt(context: tools.ToolContext) -> str:
    enabled = [tool.name for tool in tools.enabled_tools(context)]
    git_state = "available" if context.allow_git else "disabled"
    return SYSTEM_PROMPT.format(
        root=context.root,
        shell=tools.terminal.shell_description(),
        git=git_state,
    ) + f"\n\nTools available this turn: {', '.join(enabled) or 'none'}."


def _user_content(message: str, files: list[Attachment], *, images: bool = True):
    """The user turn: prompt text, plus image parts when the model can take them.

    Images are attached as real image parts so a vision model actually looks at
    them, rather than being handed base64 text and asked to imagine the picture.
    Everything else is folded into the text prompt.
    """
    prompt = build_prompt(message, files, images_as_parts=images)
    if not images:
        return prompt
    parts = image_parts(files)
    if not parts:
        return prompt
    return [{"type": "text", "text": prompt}, *parts]


def _has_images(files: list[Attachment]) -> bool:
    return bool(image_parts(files))


def _out_of_time(turn: _Turn, rounds_done: int) -> ChatResult:
    """The turn budget expired between rounds."""
    ran = ", ".join(step.name for step in turn.steps) or "nothing"
    return ChatResult(
        f"I ran out of time for this turn after {rounds_done} round(s) of tool "
        f"calls. Tools used: {ran}. Raise turn_budget_s in the Citrine config "
        "if this work legitimately needs longer.",
        turn.tokens,
        tuple(turn.steps),
    )


def _post(
    url: str,
    api_key: str,
    payload: dict,
    label: str = "provider",
    timeout: float = 180.0,
) -> tuple[dict | None, str | None]:
    """One provider request. Returns (data, error_text) - never raises."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Mcalrifle789/Citrine",
            "X-Title": "Citrine",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, _provider_error(label, exc.code, body)
    except urllib.error.URLError as exc:
        # A read timeout arrives here rather than as TimeoutError on some
        # Python/OpenSSL builds, and "network error: timed out" reads like the
        # machine is offline when it is not.
        if isinstance(exc.reason, TimeoutError):
            return None, (
                f"{label} did not respond within {timeout:.0f}s. The model may "
                "still be generating; try again, pick a faster model, or raise "
                "request_timeout_s in the Citrine config."
            )
        return None, f"{label} network error: {exc.reason}"
    except TimeoutError:
        return None, (
            f"{label} did not respond within {timeout:.0f}s. The model may still "
            "be generating; try again, pick a faster model, or raise "
            "request_timeout_s in the Citrine config."
        )
    except json.JSONDecodeError as exc:
        return None, f"{label} returned malformed JSON: {exc}"


def _rejects_tools(error: str) -> bool:
    lowered = error.lower()
    return any(term in lowered for term in ("tool", "function", "tool_choice")) and (
        "400" in lowered or "422" in lowered or "unsupported" in lowered
    )


def _rejects_images(error: str) -> bool:
    lowered = error.lower()
    return any(
        term in lowered
        for term in ("image", "vision", "content part", "multimodal")
    ) and ("400" in lowered or "422" in lowered or "unsupported" in lowered)


def _first_choice(data: dict) -> dict | None:
    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError):
        return None
    return choice if isinstance(choice, dict) else None


def _usage_tokens(data: dict) -> int:
    usage = data.get("usage") if isinstance(data, dict) else None
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int) and total > 0:
            return total
    return 0


def _assistant_message(response_message: dict, tool_calls: list) -> dict:
    """Echo the assistant turn back, tool calls included.

    Providers reject the follow-up ``tool`` messages unless the assistant
    message that requested them is present with the same ids.
    """
    return {
        "role": "assistant",
        "content": response_message.get("content") or "",
        "tool_calls": [
            {
                "id": str(call.get("id") or ""),
                "type": call.get("type") or "function",
                "function": {
                    "name": (call.get("function") or {}).get("name", ""),
                    "arguments": (call.get("function") or {}).get("arguments", "{}"),
                },
            }
            for call in tool_calls
        ],
    }


def _call_parts(call: dict) -> tuple[str, object]:
    function = call.get("function") or {}
    name = str(function.get("name") or "")
    arguments = function.get("arguments")
    if arguments is None:
        arguments = {}
    elif isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            pass  # the registry turns the malformed string into a clear result
    return name, arguments


def _summary(content: str, *, limit: int = 120) -> str:
    first = content.strip().splitlines()[0] if content.strip() else ""
    return first[:limit]


def _provider_error(label: str, status: int, body: str) -> str:
    lower = body.lower()
    if any(term in lower for term in ("quota", "credit", "insufficient", "billing")):
        reason = "credits, quota, or billing"
    elif status in {401, 403}:
        reason = "authentication"
    elif status == 429:
        reason = "rate limit"
    else:
        reason = "provider"
    return f"{label} {reason} error ({status}): {body[:700]}"


def _api_key(provider_id: str, env_var: str | None) -> str | None:
    if env_var:
        import os

        value = os.environ.get(env_var)
        if value:
            return value
    return load_secret(secret_key("provider", provider_id))

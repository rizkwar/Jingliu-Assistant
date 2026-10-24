"""Response backends, independent of the character and desktop interface."""

from collections.abc import AsyncIterator
import json

import httpx

from .config import Settings


ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class ChatError(Exception):
    """An error that can be displayed to the user."""


async def sse_payloads(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    """Handle SSE comments, event boundaries, and multi-line data fields."""
    data: list[str] = []
    async for line in lines:
        if line == "":
            if data:
                yield "\n".join(data)
                data.clear()
        elif line.startswith("data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(" ") else value)
    if data:
        yield "\n".join(data)


def api_error(status: int | None, payload: object) -> ChatError:
    hints = {
        401: "OpenRouter rejected the API key. Check OPENROUTER_API_KEY in .env.",
        402: "OpenRouter reported insufficient credits or an account limit.",
        403: "OpenRouter denied this request. Check your account's model and privacy settings.",
        404: "This model is unavailable, or it can't read the attached images or files. Check OPENROUTER_MODEL in .env.",
        429: "OpenRouter's rate limit was reached. Wait a little, then try again.",
        502: "The model provider had a problem. Try again shortly.",
        503: "No provider is available for this model right now. Try again shortly.",
    }
    if status in hints:
        return ChatError(hints[status])
    detail = ""
    if isinstance(payload, dict):
        error = payload.get("error", {})
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            detail = error["message"][:400]
    return ChatError(detail or f"OpenRouter returned an unexpected response (status {status}).")


def openrouter_message(message):
    """OpenAI-style content parts for a message with attachments; plain messages pass through."""
    files = message.get("attachments")
    if not files:
        return {"role": message["role"], "content": message["content"]}
    from .attachments import encoded, read_text
    parts = [{"type": "text", "text": message.get("content") or "(See the attached files.)"}]
    for item in files:
        if item["kind"] == "image":
            parts.append({"type": "image_url", "image_url": {"url": f"data:{item['mime']};base64,{encoded(item)}"}})
        elif item["kind"] == "pdf":
            parts.append({"type": "file", "file": {"filename": item["name"],
                                                   "file_data": f"data:application/pdf;base64,{encoded(item)}"}})
        else:
            parts.append({"type": "text", "text": read_text(item)})
    return {"role": message["role"], "content": parts}


async def stream_reply(
    client: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    settings.validate_connection()
    if settings.llm_provider == 'codex':
        from .codex_backend import stream_codex
        async for text in stream_codex(settings, messages):
            yield text
        return
    if settings.llm_provider == 'claude':
        from .claude_backend import stream_claude
        async for text in stream_claude(settings, messages):
            yield text
        return
    try:
        turns = [openrouter_message(message) for message in messages]
    except OSError as exc:
        raise ChatError("An attached file could not be read. Remove it and attach it again.") from exc
    payload = {
        "model": settings.model,
        "messages": [{"role": "system", "content": settings.system_prompt}, *turns],
        "stream": True,
        "max_tokens": 4096,
        "temperature": 0.7,
        "reasoning": {"enabled": False, "exclude": True},
    }
    try:
        async with client.stream(
            "POST",
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "X-OpenRouter-Title": "Desktop Companion",
                "Accept": "text/event-stream",
            },
            json=payload,
        ) as response:
            if response.is_error:
                body = await response.aread()
                try:
                    error_data = json.loads(body)
                except (ValueError, UnicodeError):
                    error_data = {}
                raise api_error(response.status_code, error_data)

            got_text = False
            finished = False
            async for data in sse_payloads(response.aiter_lines()):
                if data == "[DONE]":
                    finished = True
                    break
                try:
                    event = json.loads(data)
                except ValueError as exc:
                    raise ChatError("The provider sent an invalid stream. Please try again.") from exc
                if not isinstance(event, dict):
                    raise ChatError("The provider sent an unexpected stream event.")
                if "error" in event:
                    error = event["error"]
                    code = error.get("code") if isinstance(error, dict) else None
                    raise api_error(code, event)
                choices = event.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                text = (choice.get("delta") or {}).get("content")
                if isinstance(text, str) and text:
                    got_text = True
                    yield text
                reason = choice.get("finish_reason")
                if reason == "length":
                    raise ChatError("The reply reached its token limit. Ask me to continue.")
                if reason == "error":
                    raise ChatError("The provider stopped the reply with an error. Please try again.")
                if reason:
                    finished = True
            if not finished:
                raise ChatError("The connection ended before the reply finished. Please try again.")
            if not got_text:
                raise ChatError("The model returned no answer. Please try again.")
    except httpx.TimeoutException as exc:
        raise ChatError("The model took too long to respond. Please try again.") from exc
    except httpx.RequestError as exc:
        raise ChatError("Could not reach OpenRouter. Check your internet connection.") from exc


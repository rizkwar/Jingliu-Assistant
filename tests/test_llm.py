import asyncio
import json
import unittest

import httpx

from companion.config import DEFAULT_MODEL, Settings
from companion.llm import ChatError, sse_payloads, stream_reply


SETTINGS = Settings("test-key", DEFAULT_MODEL, "Jinger", "You are Jinger.")


def event(content=None, finish=None, **extra):
    delta = {} if content is None else {"content": content}
    return "data: " + json.dumps({
        "choices": [{"delta": delta, "finish_reason": finish}], **extra,
    }) + "\n\n"


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, body, status=200):
        def handler(request):
            self.request = request
            return httpx.Response(status, text=body, headers={"Content-Type": "text/event-stream"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return [text async for text in stream_reply(
                client, SETTINGS, [{"role": "user", "content": "Hello"}],
            )]

    async def test_streams_content_ignores_comments_reasoning_and_usage(self):
        body = ": OPENROUTER PROCESSING\n\n"
        body += 'data: {"choices":[{"delta":{"reasoning":"hidden"}}]}\n\n'
        body += event("Hello ") + event("there 👋", "stop")
        body += 'data: {"choices":[],"usage":{"completion_tokens":5}}\n\n'
        body += "data: [DONE]\n\n"
        self.assertEqual(await self.collect(body), ["Hello ", "there 👋"])
        payload = json.loads(self.request.content)
        self.assertEqual(payload["model"], DEFAULT_MODEL)
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "You are Jinger."})
        self.assertEqual(self.request.headers["Authorization"], "Bearer test-key")

    async def test_sse_multiline_data_and_final_event_without_blank_line(self):
        async def lines():
            for line in [": heartbeat", "event: message", 'data: {"a":', 'data: 1}', "", "data: [DONE]"]:
                yield line
        self.assertEqual([item async for item in sse_payloads(lines())], ['{"a":\n1}', "[DONE]"])

    async def test_rate_limit_has_actionable_message(self):
        with self.assertRaisesRegex(ChatError, "rate limit"):
            await self.collect('{"error":{"message":"busy"}}', 429)

    async def test_invalid_key_does_not_echo_provider_body(self):
        with self.assertRaisesRegex(ChatError, "rejected the API key"):
            await self.collect('{"error":{"message":"test-key"}}', 401)

    async def test_mid_stream_error_is_not_a_success(self):
        with self.assertRaisesRegex(ChatError, "provider had a problem"):
            await self.collect(event("Partial") + 'data: {"error":{"code":502}}\n\n')

    async def test_truncated_connection_is_not_a_success(self):
        with self.assertRaisesRegex(ChatError, "before the reply finished"):
            await self.collect(event("Partial"))

    async def test_empty_answer_is_reported(self):
        with self.assertRaisesRegex(ChatError, "no answer"):
            await self.collect(event(finish="stop") + "data: [DONE]\n\n")

    async def test_token_limit_is_reported(self):
        with self.assertRaisesRegex(ChatError, "token limit"):
            await self.collect(event("Partial", "length"))

    async def test_bad_json_is_reported(self):
        with self.assertRaisesRegex(ChatError, "invalid stream"):
            await self.collect("data: broken\n\n")

    async def test_timeout_is_reported(self):
        def handler(request):
            raise httpx.ReadTimeout("Timed out", request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ChatError, "too long"):
                _ = [chunk async for chunk in stream_reply(client, SETTINGS, [])]

    async def test_cancellation_closes_stalled_stream(self):
        entered = asyncio.Event()
        closed = asyncio.Event()

        class StalledStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                entered.set()
                await asyncio.Event().wait()
                yield b""

            async def aclose(self):
                closed.set()

        def handler(request):
            return httpx.Response(200, stream=StalledStream())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async def consume():
                return [chunk async for chunk in stream_reply(client, SETTINGS, [])]
            task = asyncio.create_task(consume())
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(closed.is_set())


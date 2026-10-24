import asyncio
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from companion import claude_backend
from companion.config import Settings, DEFAULT_MODEL
from companion.llm import ChatError, stream_reply
from companion.prompts import reply_prompt

SETTINGS = Settings('', DEFAULT_MODEL, 'Jingliu', reply_prompt('Stable Jingliu character profile.'),
                    llm_provider='claude', claude_model='sonnet')


def delta(text):
    return {'type': 'stream_event', 'event': {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': text}}}


def result(**values):
    return {'type': 'result', 'subtype': 'success', 'is_error': False, 'stop_reason': 'end_turn', **values}


class Pipe:
    def __init__(self, lines=()):
        self.lines = [json.dumps(line).encode() + b'\n' if isinstance(line, dict) else line for line in lines]
        self.written = b''
        self.closed = False

    async def readline(self):
        return self.lines.pop(0) if self.lines else b''

    def write(self, data): self.written += data
    async def drain(self): pass
    def close(self): self.closed = True


class Process:
    def __init__(self, lines):
        self.stdout, self.stdin = Pipe(lines), Pipe()
        self.returncode = None
        self.terminated = False

    def terminate(self): self.terminated = True; self.returncode = 1
    def kill(self): self.returncode = 1
    async def wait(self): return self.returncode


class ClaudeBackendTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, lines, settings=SETTINGS, messages=None):
        self.process = Process(lines)
        self.command = self.prompt = None

        async def fake_run(command, stdin_text=None, cwd=None):
            self.command, self.cwd = command, cwd
            self.prompt = Path(command[command.index('--system-prompt-file') + 1]).read_text(encoding='utf-8')
            return self.process

        with patch('companion.claude_backend.run', fake_run), \
                patch('companion.claude_backend.claude_executable', lambda: 'claude'):
            return [t async for t in stream_reply(None, settings, messages or [{'role': 'user', 'content': 'Hello'}])]

    async def test_character_is_the_whole_system_prompt_and_only_text_is_streamed(self):
        lines = [{'type': 'system', 'subtype': 'init'}, b'not json\n',
                 {'type': 'stream_event', 'event': {'type': 'content_block_delta', 'delta': {'type': 'thinking_delta', 'thinking': 'private'}}},
                 delta('Hm. '), delta('You came back.'), {'type': 'assistant', 'message': {}}, result()]
        history = [{'role': 'user', 'content': 'Earlier.'}, {'role': 'assistant', 'content': 'Earlier reply.'},
                   {'role': 'user', 'content': 'Continue.'}]
        self.assertEqual(''.join(await self.collect(lines, messages=history)), 'Hm. You came back.')
        self.assertTrue(self.prompt.startswith(SETTINGS.system_prompt))
        self.assertIn('Stable Jingliu character profile.', self.prompt)
        self.assertIn('Do not narrate actions', self.prompt)
        sent = self.process.stdin.written.decode()
        self.assertIn(json.dumps(history[:2], ensure_ascii=False), sent)
        self.assertTrue(sent.endswith('Latest user message:\nContinue.'))
        self.assertTrue(self.process.stdin.closed)
        for flag in ('--safe-mode', '--strict-mcp-config', '--no-session-persistence', '--disable-slash-commands'):
            self.assertIn(flag, self.command)
        self.assertEqual(self.command[self.command.index('--tools') + 1], '')
        self.assertEqual(self.command[self.command.index('--model') + 1], 'sonnet')
        self.assertNotIn('--system-prompt', self.command)  # Replaced through a file, never appended.

    async def test_single_message_is_sent_plainly(self):
        await self.collect([delta('Yes.'), result()])
        self.assertEqual(self.process.stdin.written.decode(), 'Hello')

    async def test_failures_are_readable(self):
        cases = [([result(is_error=True, subtype='error', result='Not logged in · Please run /login')], 'not signed in'),
                 ([{'type': 'rate_limit_event', 'rate_limit_info': {'status': 'rejected'}}], 'plan limit'),
                 ([delta('Part'), result(stop_reason='refusal')], 'declined'),
                 ([result()], 'no answer'),
                 ([delta('Cut')], 'stopped before'),
                 ([{'type': 'stream_event', 'event': {'type': 'content_block_start', 'content_block': {'type': 'tool_use'}}}], 'tool operation')]
        for lines, message in cases:
            with self.subTest(message), self.assertRaisesRegex(ChatError, message):
                await self.collect(lines)

    async def test_process_is_stopped_on_cancellation(self):
        with self.assertRaises(asyncio.CancelledError):
            async def cancelled(): raise asyncio.CancelledError
            self.process = None
            lines = Process([])
            lines.stdout.readline = cancelled
            async def fake_run(command, stdin_text=None, cwd=None): return lines
            with patch('companion.claude_backend.run', fake_run), \
                    patch('companion.claude_backend.claude_executable', lambda: 'claude'):
                _ = [t async for t in stream_reply(None, SETTINGS, [{'role': 'user', 'content': 'Hi'}])]
        self.assertTrue(lines.terminated)

    def test_child_never_sees_api_keys(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'x', 'ANTHROPIC_AUTH_TOKEN': 'y', 'OPENROUTER_API_KEY': 'z',
                                       'CLAUDECODE': '1', 'CLAUDE_CODE_ENTRYPOINT': 'cli', 'PATH': 'kept'}):
            environment = claude_backend.child_environment()
        self.assertEqual({k for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'OPENROUTER_API_KEY',
                                      'CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT') if k in environment}, set())
        self.assertEqual(environment['PATH'], 'kept')

    async def test_account_reports_only_sign_in_and_plan(self):
        class Status(Process):
            async def communicate(self):
                return json.dumps({'loggedIn': True, 'email': 'private@example.com', 'orgId': 'private',
                                   'subscriptionType': 'max'}).encode(), b''
        async def fake_run(command, stdin_text=None, cwd=None): return Status([])
        with patch('companion.claude_backend.run', fake_run), \
                patch('companion.claude_backend.claude_executable', lambda: 'claude'):
            self.assertEqual(await claude_backend.account(), {'signed_in': True, 'plan': 'max'})

    def test_validation_needs_no_api_key(self):
        SETTINGS.validate_connection()
        self.assertFalse(SETTINGS.missing_key())
        with self.assertRaises(ValueError):
            replace(SETTINGS, claude_model='bad model').validate_connection()

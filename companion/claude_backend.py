"""Local Claude Code transport. Uses the Claude subscription the CLI is signed in with."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .attachments import content_blocks
from .llm import ChatError


DEFAULT_CLAUDE_MODEL = 'claude-sonnet-5-5'
CLAUDE_MODELS = (
    ('Claude Sonnet 5.5', 'claude-sonnet-5-5'),
    ('Claude Opus 5.5', 'claude-opus-5-5'),
    ('Claude Haiku 5.5', 'claude-haiku-5-5'),
    ('Claude Fable 5.1', 'claude-fable-5-1'),
)
# Earlier builds saved Claude Code family aliases; show them as their pinned versions.
LEGACY_ALIASES = {'sonnet': 'claude-sonnet-5-5', 'opus': 'claude-opus-5-5',
                  'haiku': 'claude-haiku-5-5', 'fable': 'claude-fable-5-1'}
TRANSPORT_NOTE = (
    '\n\nTransport note: the user turn may begin with earlier messages of this conversation as JSON, '
    'oldest first, followed by the latest user message. Treat them as the conversation so far and write '
    'only your next reply to the latest message. Never quote the JSON or mention this format. '
    'Images, PDFs and <attached_file> blocks in the latest message are things the user shared with you now; '
    'you can see and read them. "[Attached …]" lines in earlier messages mark files shared before, '
    'which are no longer visible to you.'
)


def claude_executable():
    executable = shutil.which('claude.exe' if os.name == 'nt' else 'claude')
    home = os.environ.get('USERPROFILE' if os.name == 'nt' else 'HOME')
    if not executable and home:
        candidate = Path(home) / '.local/bin' / ('claude.exe' if os.name == 'nt' else 'claude')
        if candidate.is_file(): executable = str(candidate)
    if not executable:
        raise ChatError('Claude Code is not installed or could not be found. Install it, then restart the assistant.')
    return executable


def child_environment():
    # A configured API key would bill the API instead of the subscription.
    environment = dict(os.environ)
    for name in list(environment):
        if (name.endswith(('API_KEY', 'AUTH_TOKEN')) or name in {'HF_TOKEN', 'ANTHROPIC_BASE_URL', 'CLAUDECODE'}
                or name.startswith('CLAUDE_CODE_')):
            environment.pop(name, None)
    return environment


def reply_command(prompt_file, model):
    # Conversation only: no tools, MCP, skills, CLAUDE.md, hooks or saved sessions.
    return [claude_executable(), '-p', '--system-prompt-file', str(prompt_file), '--tools', '',
            '--safe-mode', '--strict-mcp-config', '--disable-slash-commands', '--no-session-persistence',
            '--model', model or DEFAULT_CLAUDE_MODEL, '--effort', 'low', '--input-format', 'stream-json',
            '--output-format', 'stream-json', '--verbose', '--include-partial-messages']


def user_turn(messages):
    """One stream-json user message: prior turns as JSON text, the latest text, then its attachments."""
    latest = messages[-1] if messages else {}
    files = latest.get('attachments') or []
    turns = [{'role': m['role'], 'content': m['content']} for m in messages[:-1]
             if m.get('role') in {'user', 'assistant'} and m.get('content')]
    if latest.get('role') != 'user' or not (latest.get('content') or files):
        raise ChatError('There is no message to reply to.')
    text = latest.get('content') or ''
    if turns:
        text = ('Earlier messages (JSON):\n' + json.dumps(turns, ensure_ascii=False)
                + '\n\nLatest user message:\n' + (text or '(attachments only)'))
    try:
        content = content_blocks(text, files)
    except OSError:
        raise ChatError('An attached file could not be read. Remove it and attach it again.') from None
    return json.dumps({'type': 'user', 'message': {'role': 'user', 'content': content}}, ensure_ascii=False) + '\n'


def result_error(event):
    text = str(event.get('result') or '').lower()
    if 'login' in text or 'logged in' in text or 'auth' in text:
        return ChatError('Claude Code is not signed in. Use Sign in to Claude in Settings, then try again.')
    if 'limit' in text:
        return ChatError('Your Claude plan limit was reached. Wait for it to reset, then try again.')
    return ChatError('Claude Code could not finish the reply. Check sign-in and your plan limits.')


async def run(command, stdin_text=None, cwd=None):
    return await asyncio.create_subprocess_exec(
        *command, cwd=cwd, env=child_environment(), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=2**22,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


async def stop(process):
    if process.returncode is not None: return
    process.terminate()
    try: await asyncio.wait_for(process.wait(), 2)
    except asyncio.TimeoutError:
        process.kill(); await process.wait()


async def account():
    """Signed-in state and plan type only; never the email or organization."""
    try:
        process = await run([claude_executable(), 'auth', 'status'])
    except OSError:
        raise ChatError('Could not start Claude Code. Check its installation.') from None
    try:
        output, _ = await process.communicate()
    finally:
        await stop(process)
    try:
        status = json.loads(output)
    except (ValueError, UnicodeError):
        raise ChatError('Claude Code returned an unexpected sign-in status. Update it and try again.') from None
    return {'signed_in': bool(status.get('loggedIn')), 'plan': str(status.get('subscriptionType') or '')}


def open_login():
    """Claude Code owns sign-in; it runs in its own console window."""
    options = {'creationflags': subprocess.CREATE_NEW_CONSOLE} if os.name == 'nt' else {}
    try:
        subprocess.Popen([claude_executable(), 'auth', 'login', '--claudeai'], env=child_environment(), **options)
    except OSError:
        raise ChatError('Could not start Claude Code sign-in. Run "claude auth login" in a terminal.') from None


async def stream_claude(settings, messages):
    prompt = user_turn(messages)
    with tempfile.TemporaryDirectory(prefix='companion-claude-') as folder:
        prompt_file = Path(folder) / 'system-prompt.txt'
        prompt_file.write_text(settings.system_prompt + TRANSPORT_NOTE, encoding='utf-8')
        try:
            process = await run(reply_command(prompt_file, settings.claude_model), cwd=folder)
        except OSError:
            raise ChatError('Could not start Claude Code. Check its installation and restart the assistant.') from None
        try:
            process.stdin.write(prompt.encode('utf-8'))
            await process.stdin.drain()
            process.stdin.close()
            got_text = False
            while True:
                line = await process.stdout.readline()
                if not line:
                    raise ChatError('Claude Code stopped before the reply finished. Please try again.')
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    continue  # Non-JSON diagnostics are not part of the reply.
                kind = event.get('type')
                if kind == 'stream_event':
                    inner = event.get('event') or {}
                    if inner.get('type') == 'content_block_start' and (inner.get('content_block') or {}).get('type') in {
                            'tool_use', 'server_tool_use', 'mcp_tool_use'}:
                        raise ChatError('Claude attempted a tool operation. Conversation was stopped; tools are not enabled here.')
                    delta = inner.get('delta') or {}
                    if inner.get('type') == 'content_block_delta' and delta.get('type') == 'text_delta' and delta.get('text'):
                        got_text = True
                        yield delta['text']
                elif kind == 'rate_limit_event' and (event.get('rate_limit_info') or {}).get('status') == 'rejected':
                    raise ChatError('Your Claude plan limit was reached. Wait for it to reset, then try again.')
                elif kind == 'result':
                    if event.get('is_error') or event.get('subtype') != 'success':
                        raise result_error(event)
                    if event.get('stop_reason') == 'refusal':
                        raise ChatError('Claude declined to continue this reply. Try rephrasing, or start a New conversation.')
                    if event.get('stop_reason') == 'max_tokens':
                        raise ChatError('The reply reached its token limit. Ask me to continue.')
                    if not got_text:
                        raise ChatError('Claude returned no answer. Please try again.')
                    return
        finally:
            await stop(process)

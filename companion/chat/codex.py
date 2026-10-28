"""Local Codex app-server transport. ChatGPT login stays in its own private profile."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from ..core.config import PROJECT_ROOT
from .llm import ChatError


def codex_executable():
    executable = shutil.which('codex.exe' if os.name == 'nt' else 'codex')
    if not executable and os.name == 'nt':
        candidate = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/OpenAI/Codex/bin/codex.exe'
        if candidate.is_file(): executable = str(candidate)
    if not executable:
        raise ChatError('Codex is not installed or could not be found. Install Codex CLI, then restart the assistant.')
    return executable


def server_command():
    # This profile is app-owned: no developer workspace, plugins or custom rules.
    disabled = ['shell_tool', 'unified_exec', 'code_mode', 'code_mode_only', 'code_mode_host',
                'apply_patch_freeform', 'view_image', 'apps', 'plugins', 'hooks', 'codex_hooks',
                'memories', 'memory_tool', 'multi_agent', 'multi_agent_v2', 'js_repl',
                'browser_use', 'computer_use', 'image_generation', 'search_tool', 'tool_search',
                'skill_search', 'goals', 'request_permissions', 'request_permissions_tool', 'tool_suggest']
    options = [f'features.{name}=false' for name in disabled] + [
        'features.skip_host_skill_discovery=true', 'web_search="disabled"',
        'tools.update_plan.enabled=false', 'tools.experimental_request_user_input.enabled=false',
        'agents.enabled=false', 'project_doc_max_bytes=0', 'history.persistence="none"',
        'forced_login_method="chatgpt"', 'model_provider="openai"', 'analytics.enabled=false']
    return [codex_executable(), 'app-server', '--listen', 'stdio://',
            *[part for value in options for part in ('-c', value)]]


class CodexServer:
    def __init__(self, process):
        self.process = process
        self.sequence = 0

    async def send(self, payload):
        self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + '\n').encode())
        await self.process.stdin.drain()

    async def receive(self):
        line = await self.process.stdout.readline()
        if not line: raise ChatError('Codex stopped unexpectedly. Check its installation and sign in again.')
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            raise ChatError('Codex returned an invalid response. Update Codex and try again.') from None
        if not isinstance(event, dict): raise ChatError('Codex returned an unexpected response.')
        if 'method' in event and 'id' in event:
            await self.send({'id':event['id'], 'error':{'code':-32601, 'message':'Tools and approvals are unavailable in this companion.'}})
            raise ChatError('Codex requested an unsupported tool. This companion supports conversation only.')
        return event

    async def rpc(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        await self.send({'id':request_id, 'method':method, 'params':params})
        while True:
            event = await self.receive()
            if event.get('id') == request_id:
                if 'error' in event:
                    raise ChatError('Codex could not complete this request. Check sign-in, model access and your plan limits.')
                return event.get('result', {})


@asynccontextmanager
async def server():
    profile = PROJECT_ROOT / 'data/codex-profile'
    profile.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, CODEX_HOME=str(profile))
    for name in list(environment):
        if name.endswith('API_KEY') or name in {'HF_TOKEN', 'ACCESS_TOKEN', 'CODEX_ACCESS_TOKEN'}:
            environment.pop(name, None)
    with tempfile.TemporaryDirectory(prefix='companion-codex-') as folder:
        try:
            process = await asyncio.create_subprocess_exec(*server_command(), cwd=folder, env=environment,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=2**20,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except OSError:
            raise ChatError('Could not start Codex. Check its installation and restart the assistant.') from None
        connection = CodexServer(process)
        try:
            await connection.rpc('initialize', {'clientInfo':{'name':'desktop_companion', 'title':'Desktop Companion', 'version':'1.0'},
                                               'capabilities':{'experimentalApi':True}})
            await connection.send({'method':'initialized','params':{}})
            yield connection, folder
        finally:
            if process.stdin: process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 2)
            except asyncio.TimeoutError:
                process.terminate()
                try: await asyncio.wait_for(process.wait(), 2)
                except asyncio.TimeoutError:
                    process.kill(); await process.wait()


async def account_and_models(connection):
    result = await connection.rpc('account/read', {'refreshToken':False})
    account = result.get('account') or {}
    # Never return an email, account identifier or any credential to the UI/logs.
    signed_in = account.get('type') == 'chatgpt'
    models = []
    cursor = None
    for _ in range(10):
        response = await connection.rpc('model/list', {'limit':100, 'includeHidden':False, 'cursor':cursor})
        for model in response.get('data', []):
            if isinstance(model.get('model'), str):
                models.append({'id':model['model'], 'name':model.get('displayName', model['model'])})
        cursor = response.get('nextCursor')
        if not cursor: break
    return {'signed_in':signed_in, 'models':models}


async def connect(login=False, browser=None):
    async with server() as (connection, _):
        result = await account_and_models(connection)
        if login and not result['signed_in']:
            response = await connection.rpc('account/login/start', {'type':'chatgpt'})
            url = response.get('authUrl', '')
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname not in {'auth.openai.com', 'chatgpt.com', 'auth0.openai.com'}:
                raise ChatError('Codex did not provide a recognized ChatGPT sign-in address.')
            if browser: browser(url)
            while True:
                event = await connection.receive()
                if event.get('method') == 'account/login/completed':
                    if not event.get('params', {}).get('success'):
                        raise ChatError('ChatGPT sign-in did not complete. Try again from Settings.')
                    break
            result = await account_and_models(connection)
        return result


async def read_limits():
    """The ChatGPT plan's rate limit windows (Codex's RateLimitSnapshot), read without a reply."""
    async with server() as (connection, _):
        account = (await connection.rpc('account/read', {'refreshToken':False})).get('account') or {}
        if account.get('type') != 'chatgpt':
            raise ChatError('Sign in to ChatGPT from Settings to see your Codex limits.')
        return (await connection.rpc('account/rateLimits/read', None)).get('rateLimits') or {}


async def stream_codex(settings, messages):
    async with server() as (connection, folder):
        account = (await connection.rpc('account/read', {'refreshToken':False})).get('account') or {}
        if account.get('type') != 'chatgpt':
            raise ChatError('Sign in to ChatGPT from Settings first. This option uses your Codex subscription access.')
        params = {'cwd':folder, 'ephemeral':True, 'sandbox':'read-only', 'approvalPolicy':'never',
                  'baseInstructions':settings.system_prompt, 'developerInstructions':
                  'Respond only as the configured desktop character. Conversation only: do not use tools, inspect files, browse, or execute commands. '
                  'The input JSON contains ordered prior messages and the latest user message; continue that conversation. '
                  'Do not quote the JSON or explain the transport. Never output reasoning or tool commentary.',
                  'personality':'none', 'environments':[], 'dynamicTools':[], 'allowProviderModelFallback':False}
        if settings.codex_model: params['model'] = settings.codex_model
        files = (messages[-1].get('attachments') or []) if messages else []
        if any(item['kind'] == 'pdf' for item in files):
            raise ChatError('PDFs are not supported with Codex here. Switch to Claude in Settings to share PDFs.')
        history = [{'role':m['role'], 'content':m['content']} for m in messages]
        if history and messages[-1].get('context'):  # Last, so everything before it stays the same and is cached.
            history[-1]['content'] = messages[-1]['context'] + '\n\n' + history[-1]['content']
        try:
            from .attachments import read_text
            for item in files:
                if item['kind'] == 'text': history[-1]['content'] += '\n\n' + read_text(item)
        except OSError:
            raise ChatError('An attached file could not be read. Remove it and attach it again.') from None
        response = await connection.rpc('thread/start', params)
        thread = response['thread']['id']
        images = [{'type':'localImage', 'path':item['path']} for item in files if item['kind'] == 'image']
        from .effort import codex as codex_effort
        turn = {'threadId':thread, 'input':[{'type':'text',
            'text':json.dumps(history, ensure_ascii=False), 'text_elements':[]}, *images],
            'sandboxPolicy':{'type':'readOnly','networkAccess':False},
            'effort':codex_effort(getattr(settings, 'effort', 'low'))}
        try:
            await connection.rpc('turn/start', turn)
        except ChatError:
            turn.pop('effort')  # A model that does not offer this effort still answers at its own.
            await connection.rpc('turn/start', turn)
        phases, streamed = {}, set()
        got_text = False
        tokens = None
        while True:
            event = await connection.receive()
            method, values = event.get('method'), event.get('params', {})
            if values.get('threadId', thread) != thread: continue
            item = values.get('item', {})
            if method in {'item/started', 'item/completed'}:
                kind = item.get('type')
                if kind == 'agentMessage':
                    phases[item['id']] = item.get('phase')
                    if method == 'item/completed' and item['id'] not in streamed and item.get('phase') in {None, 'final_answer'}:
                        text = item.get('text', '')
                        if text: got_text = True; yield text
                elif kind in {'commandExecution','fileChange','mcpToolCall','webSearch','imageGeneration','dynamicToolCall'}:
                    raise ChatError('Codex attempted a tool operation. Conversation was stopped; tools are not enabled here.')
            elif method == 'item/agentMessage/delta' and phases.get(values.get('itemId')) == 'final_answer':
                text = values.get('delta', '')
                if text:
                    got_text = True; streamed.add(values['itemId']); yield text
            elif method == 'thread/tokenUsage/updated':
                tokens = (values.get('tokenUsage') or {}).get('total') or tokens
            elif method == 'account/rateLimits/updated':
                from .usage import codex_windows
                windows = codex_windows(values.get('rateLimits'))
                if windows: yield {'limits': windows}
            elif method == 'turn/completed':
                if values.get('turn', {}).get('status') != 'completed':
                    raise ChatError('Codex could not finish the reply. Check model access and your subscription limits; no alternate provider was used.')
                if not got_text: raise ChatError('Codex returned no conversational answer. Please try again.')
                if tokens:
                    cached = tokens.get('cachedInputTokens') or 0
                    yield {'usage': {'model':settings.codex_model or '', 'cached':cached,
                                     'input':max(0, (tokens.get('inputTokens') or 0) - cached),
                                     'output':tokens.get('outputTokens') or 0}}
                return
            elif method == 'error':
                raise ChatError('Codex reported an error. Check sign-in, model access and your subscription limits.')

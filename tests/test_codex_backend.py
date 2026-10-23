import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from companion.codex_backend import CodexServer, stream_codex, account_and_models
from companion.config import Settings, DEFAULT_MODEL
from companion.llm import ChatError, stream_reply

SETTINGS = Settings('', DEFAULT_MODEL, 'Jingliu', 'Stable character profile plus memory notes.',
                    llm_provider='codex', codex_model='chosen-model')


class Connection:
    def __init__(self, events=(), auth='chatgpt'):
        self.events = list(events)
        self.auth = auth
        self.calls = []

    async def rpc(self, method, params):
        self.calls.append((method, params))
        return {'account':{'type':self.auth}} if method == 'account/read' else (
            {'thread':{'id':'thread'}} if method == 'thread/start' else {})

    async def receive(self):
        return self.events.pop(0)


def event(method, **params):
    return {'method':method,'params':{'threadId':'thread',**params}}


class CodexBackendTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, connection, messages=None):
        @asynccontextmanager
        async def fake_server():
            yield connection, 'empty-workspace'
        with patch('companion.codex_backend.server', fake_server):
            return [text async for text in stream_reply(None, SETTINGS, messages or [{'role':'user','content':'Hello'}])]

    async def test_character_and_history_are_supplied_while_only_final_answer_is_streamed(self):
        connection = Connection([
            event('item/started', item={'id':'analysis','type':'agentMessage','phase':'commentary'}),
            event('item/agentMessage/delta', itemId='analysis', delta='Private commentary'),
            event('item/completed', item={'id':'analysis','type':'agentMessage','phase':'commentary','text':'Private commentary'}),
            event('item/started', item={'id':'answer','type':'agentMessage','phase':'final_answer'}),
            event('item/agentMessage/delta', itemId='answer', delta='You have '),
            event('item/agentMessage/delta', itemId='answer', delta='my attention.'),
            event('item/completed', item={'id':'answer','type':'agentMessage','phase':'final_answer','text':'You have my attention.'}),
            event('turn/completed', turn={'status':'completed'}),
        ])
        history=[{'role':'assistant','content':'Earlier shared discussion.'}, {'role':'user','content':'Continue.'}]
        answer=await self.collect(connection, history)
        self.assertEqual(''.join(answer),'You have my attention.')
        start=next(p for m,p in connection.calls if m=='thread/start')
        self.assertEqual(start['baseInstructions'],SETTINGS.system_prompt)
        self.assertEqual(start['model'],'chosen-model')
        self.assertFalse(start['allowProviderModelFallback'])
        self.assertTrue(start['ephemeral'])
        self.assertEqual(start['personality'],'none')
        self.assertEqual(start['environments'],[])
        turn=next(p for m,p in connection.calls if m=='turn/start')
        self.assertEqual(json.loads(turn['input'][0]['text']),history)

    async def test_nonstreaming_final_message_is_not_lost(self):
        connection=Connection([event('item/completed',item={'type':'agentMessage','id':'answer','text':'A natural answer.'}),
                               event('turn/completed',turn={'status':'completed'})])
        self.assertEqual(await self.collect(connection),['A natural answer.'])

    async def test_api_key_account_is_not_a_subscription_fallback(self):
        with self.assertRaisesRegex(ChatError,'Sign in'):
            await self.collect(Connection(auth='apiKey'))

    async def test_subscription_limit_or_model_failure_does_not_switch_provider(self):
        with self.assertRaisesRegex(ChatError,'no alternate provider'):
            await self.collect(Connection([event('turn/completed',turn={'status':'failed'})]))

    async def test_tool_operation_is_rejected(self):
        with self.assertRaisesRegex(ChatError,'tool operation'):
            await self.collect(Connection([event('item/started',item={'id':'tool','type':'commandExecution'})]))

    async def test_cancellation_propagates(self):
        connection=Connection()
        async def cancelled(): raise asyncio.CancelledError
        connection.receive=cancelled
        with self.assertRaises(asyncio.CancelledError): await self.collect(connection)

    async def test_account_result_omits_private_identity(self):
        connection=Connection()
        async def rpc(method, params):
            return {'account':{'type':'chatgpt','email':'private@example.com','id':'private-id'}} if method=='account/read' else {
                'data':[{'model':'model-a','displayName':'Model A'}]}
        connection.rpc=rpc
        self.assertEqual(await account_and_models(connection),{'signed_in':True,'models':[{'id':'model-a','name':'Model A'}]})

    def test_codex_validation_does_not_need_openrouter_key(self):
        SETTINGS.validate_connection()
        with self.assertRaises(ValueError): replace(SETTINGS,codex_model='bad model').validate_connection()

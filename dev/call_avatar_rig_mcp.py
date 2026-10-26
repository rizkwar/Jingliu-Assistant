"""Call the registered project's STDIO MCP from JSON on stdin.

Useful when the current Codex conversation has not reloaded the tool catalogue.
This uses real MCP initialization/discovery/calls, not direct function dispatch.
Input: [{"tool":"rig_status","arguments":{}}].
"""
import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    workspace=Path(__file__).resolve().parent.parent
    calls=json.load(sys.stdin)
    if not isinstance(calls,list) or not 1 <= len(calls) <= 20:
        raise ValueError('Supply 1..20 MCP calls.')
    params=StdioServerParameters(command=sys.executable,args=[str(workspace/'dev/avatar_rig_mcp.py'),
                               '--root',str(workspace/'.cache/avatar-authoring/jingliu')])
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            available={t.name for t in (await session.list_tools()).tools}
            for call in calls:
                if call['tool'] not in available:
                    raise ValueError('Unknown MCP tool.')
                result=await session.call_tool(call['tool'],call.get('arguments',{}))
                if result.isError:
                    raise ValueError(str(result.content))
                body=result.structuredContent or json.loads(next(c.text for c in result.content if c.type=='text'))
                print(json.dumps({'tool':call['tool'],'result':body}))


if __name__=='__main__':
    asyncio.run(main())

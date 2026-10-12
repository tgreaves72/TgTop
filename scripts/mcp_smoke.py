"""Exercise real MCP stdio protocol against isolated demo service, without printing tokens."""
import asyncio
import os
import sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.stdio import stdio_client,StdioServerParameters

async def main():
    url='http://127.0.0.1:8766'
    with httpx.Client(base_url=url,headers={'Origin':url,'X-TgTop':'1'}) as c:
        c.post('/api/login',json={'username':'tyler','password':'demo-workspace-2026','device':'MCP smoke test'}).raise_for_status()
        grant=c.post('/api/mcp-token',json={}).json()
        params=StdioServerParameters(command=sys.executable,args=['-m','app.mcp_server'],cwd=str(Path(__file__).resolve().parent.parent),env={**os.environ,'TGTOP_URL':url,'TGTOP_MCP_TOKEN':grant['token']})
        try:
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    listing=await session.list_tools()
                    assert {t.name for t in listing.tools}=={'search_context','create_task','create_reminder'}
                    result=await session.call_tool('search_context',{'query':'Website'})
                    assert not result.is_error
                    print('MCP protocol initialize, tool listing, and authorized context call passed')
        finally:
            c.post('/api/devices/'+grant['device_id']+'/revoke',json={}).raise_for_status()

asyncio.run(main())

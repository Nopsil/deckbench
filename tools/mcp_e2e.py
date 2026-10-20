"""MCP 服务器端到端测试：用官方 MCP 客户端分别走 stdio 和 streamable-HTTP，打几步、auto、undo、核对日志。
  python tools/mcp_e2e.py [--http-url http://127.0.0.1:8765/mcp]
"""
import argparse
import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


async def scenario(session, tag):
    async def call(name, **kw):
        r = await session.call_tool(name, kw)
        txt = "".join(getattr(c, "text", "") for c in r.content)
        if r.isError:
            raise RuntimeError(f"{name} error: {txt}")
        return txt
    tools = [t.name for t in (await session.list_tools()).tools]
    print(f"[{tag}] tools:", tools)
    t = await call("new_run", seed="qianwenniang", character="Ironclad", ascension=10, persona="qianwen")
    print(t[:900])
    assert "Q1ANWENN1ANG" in t, "种子不对"
    t = await call("act", option_index=0, reason="第一个Neow选项，赌一把！")
    print(t[:300])
    assert not t.startswith("❌"), t[:300]
    t = await call("act", option_index=99, reason="故意填错")
    assert t.startswith("❌"), "非法选项应报错"
    t = await call("get_map")
    print(t[:400])
    t = await call("act", option_index=0, reason="走最左边")
    t = await call("auto", until="combat_end")
    print(t[:600])
    log1 = await call("get_log", last=50)
    n_before = log1.count("\n") + 1
    t = await call("undo", steps=2)
    print("UNDO ->", t[:120])
    assert f"决策 #{n_before - 2}" in t, "undo 后应停在少 2 步的位置"
    log2 = await call("get_log", last=50)
    assert log2.count("\n") + 1 == n_before - 2, "undo 后应少 2 步"
    exp = json.loads(await call("export_log"))
    rows = [json.loads(l) for l in open(exp["files"]["decisions.jsonl"], encoding="utf-8")]
    reasons = [r.get("reason") for r in rows if r.get("source") == "replay" or r.get("source") == "external"]
    assert "第一个Neow选项，赌一把！" in reasons, "理由没写进 decision_log"
    print(f"[{tag}] export:", json.dumps(exp, ensure_ascii=False)[:400])
    print(f"[{tag}] list_runs:\n" + (await call("list_runs"))[-400:])
    # lirixuan 风格：auto 代打用 style.py 规则，打到第 1 幕首领前不出错
    t = await call("new_run", seed="R1", character="Ironclad", ascension=0, persona="lirixuan")
    t = await call("auto", steps=400, until="screen:shop")
    assert "❌" not in t and "fatal" not in t.lower(), t[-500:]
    print(f"[{tag}] lirixuan auto ->", t[:160].replace("\n", " | "))
    print(f"[{tag}] OK: {len(rows)} 行日志，{exp['decisions']} 个决策")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http-url", default="")
    a = ap.parse_args()
    from mcp import ClientSession
    if a.http_url:
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(a.http_url) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                await scenario(s, "http")
    else:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        p = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, "mcp_server.py")], env=dict(os.environ))
        async with stdio_client(p) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                await scenario(s, "stdio")


if __name__ == "__main__":
    asyncio.run(main())

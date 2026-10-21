"""端到端界面测试（开发用）：先启动 `python -m gui.app --serve --port 8765`，再运行本脚本（会把界面语言设成简体中文）。
用 Playwright 逐页操作并截图到 SHOTS 目录。"""
import asyncio
import json
import os
import sys
import time
import urllib.request

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8765"
SHOTS = sys.argv[1] if len(sys.argv) > 1 else "gui-shots"
ZIP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples", "demo_mod.zip")
os.makedirs(SHOTS, exist_ok=True)


def api(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"}, method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(req))


def wait_done(rid, timeout=600):
    t = time.time()
    while time.time() - t < timeout:
        m = api(f"/api/runs/{rid}")
        if m["status"] != "running":
            return m
        time.sleep(1)
    raise TimeoutError(rid)


async def shot(pg, name, full=False):
    await pg.wait_for_timeout(900)
    await pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=full)
    print("shot", name, flush=True)


async def main():
    errors = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 800})
        pg = await ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        api("/api/settings", {"lang": "zhs"})   # 下面按中文界面文字定位
        await pg.goto(BASE + "/#/new")
        await pg.evaluate("""localStorage.setItem('ui.lang', 'zhs'); localStorage.setItem('nt.form', JSON.stringify({b: {char: 'Claude', asc: 0, n: 60, start: 0, procs: 2,
            agent: 'heuristic', variants: [], force: [], replace: []}})); localStorage.setItem('nt.kind', 'batch')""")
        await pg.reload()
        await pg.wait_for_selector("text=角色与难度", timeout=120000)
        await shot(pg, "01_新建测试_整局批量")
        # 强制加入：搜索「已核实」并选中，再切成升级版
        sel = pg.locator(".panel:has-text('起始牌组调整') .n-select").first
        await sel.click()
        await pg.keyboard.type("已核实")
        await pg.wait_for_timeout(500)
        await pg.keyboard.press("Enter")
        await pg.wait_for_timeout(400)
        await pg.locator(".panel:has-text('起始牌组调整') button.up").first.click()
        # 移除一张打击
        sel2 = pg.locator(".panel:has-text('起始牌组调整') .n-select").nth(1)
        await sel2.click()
        await pg.keyboard.type("CLAUDE_STRIKE")
        await pg.wait_for_timeout(400)
        await pg.keyboard.press("Enter")
        await pg.locator(".panel:has-text('起始牌组调整')").scroll_into_view_if_needed()
        await shot(pg, "02_新建测试_选牌")
        await pg.click("text=开始运行")
        await pg.wait_for_url("**/#/run/*", timeout=20000)
        rid_b = pg.url.split("/run/")[1]
        await pg.wait_for_timeout(9000)
        await shot(pg, "03_运行中")
        # 基线（同一批种子，不加牌），通过 API 启动
        base = api("/api/runs", {"kind": "batch", "title": "Claude娘 A0 × 60 基线", "params": {"char": "Claude", "asc": 0, "n": 60, "start": 0, "procs": 5, "agent": "heuristic", "variants": [], "force": [], "replace": []}})
        mb = wait_done(rid_b)
        assert mb["status"] == "done", mb
        await pg.wait_for_selector("text=查看报告", timeout=30000)
        await shot(pg, "04_运行完成")
        await pg.click("text=查看报告")
        await pg.wait_for_selector("text=层数存活曲线", timeout=20000)
        await shot(pg, "05_报告_整局批量")
        await shot(pg, "05b_报告_整局批量_整页", full=True)
        ma = wait_done(base["id"])
        assert ma["status"] == "done", ma
        await pg.goto(f"{BASE}/#/ab?a={base['id']}&b={rid_b}")
        await pg.wait_for_selector("text=并排数值", timeout=20000)
        await shot(pg, "06_单卡AB")
        await shot(pg, "06b_单卡AB_整页", full=True)
        # 战斗实验 + 上传 mod
        await pg.goto(BASE + "/#/new")
        await pg.click("text=战斗实验")
        await pg.wait_for_selector("text=上传 mod")
        async with pg.expect_file_chooser() as fc:
            await pg.click("text=选择 zip…")
        await (await fc.value).set_files(ZIP)
        await pg.wait_for_selector("text=示例 mod：剑客", timeout=60000)
        await pg.wait_for_timeout(800)
        # 选卡组：剑客两组 + 铁甲起始
        for name in ("剑客·起始", "剑客·连斩流", "铁甲战士·起始"):
            await pg.locator(f".decks .n-checkbox:has-text('{name}')").first.click()
        fights = pg.locator(".panel:has-text('规模与 AI') input").first
        await fights.fill("40")
        await fights.press("Tab")
        await shot(pg, "07_新建测试_战斗实验_上传mod")
        await shot(pg, "07b_新建测试_战斗实验_整页", full=True)
        await pg.click("text=开始运行")
        await pg.wait_for_url("**/#/run/*", timeout=20000)
        rid_c = pg.url.split("/run/")[1]
        mc = wait_done(rid_c)
        assert mc["status"] == "done", mc
        await pg.goto(f"{BASE}/#/report/{rid_c}")
        await pg.wait_for_selector("text=各卡组胜率", timeout=20000)
        await shot(pg, "08_报告_战斗实验")
        await pg.click("text=完整报告（report.md）")
        await pg.wait_for_timeout(800)
        await shot(pg, "09_报告_reportmd")
        # 预设实验（quick）跑两次不同种子，做战斗 A/B
        r1 = api("/api/runs", {"kind": "combat", "params": {"preset": "quick", "fights": 20, "seed": 1, "agent": "heuristic", "procs": 6}})
        wait_done(r1["id"])
        r2 = api("/api/runs", {"kind": "combat", "params": {"preset": "quick", "fights": 20, "seed": 2, "agent": "heuristic", "procs": 6}})
        wait_done(r2["id"])
        await pg.goto(f"{BASE}/#/ab?a={r1['id']}&b={r2['id']}")
        await pg.wait_for_selector("text=各格子胜率差", timeout=20000)
        await shot(pg, "10_AB_战斗实验")
        # 取消
        big = api("/api/runs", {"kind": "batch", "params": {"char": "Ironclad", "asc": 10, "n": 300, "start": 0, "procs": 2, "agent": "heuristic"}})
        await pg.goto(f"{BASE}/#/run/{big['id']}")
        await pg.wait_for_timeout(5000)
        await pg.click("text=取消运行")
        await pg.click(".n-popconfirm__action button:has-text('确认')")
        mx = wait_done(big["id"], 60)
        assert mx["status"] == "cancelled", mx
        await pg.wait_for_timeout(1500)
        await shot(pg, "11_已取消")
        # 历史记录 + 重跑
        await pg.goto(BASE + "/#/history")
        await pg.wait_for_selector("text=打开报告", timeout=20000)
        await shot(pg, "12_历史记录")
        await pg.goto(BASE + "/#/run")
        await pg.wait_for_timeout(1500)
        await shot(pg, "13_运行中_空")
        await b.close()
    print("console errors:", errors)


asyncio.run(main())

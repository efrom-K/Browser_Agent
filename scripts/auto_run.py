"""Autonomous run with full logging and a watchdog.

usage: python scripts/auto_run.py NAME "task" [--headless] [--max-steps N] [--max-minutes M] [--start URL]

Writes runs/<NAME>/steps.jsonl (every LLM call: observation it saw, response,
tokens, latency), step screenshots, and result.json. Aborts on captcha/IP
block (screenshot saved, no further requests), on a stuck model (repeated
WARNINGs), and on wall-clock timeout.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.browser.controller import BrowserController
from agent.core.llm_client import LLMClient
from agent.core.loop import AgentLoop

ap = argparse.ArgumentParser()
ap.add_argument("name")
ap.add_argument("task")
ap.add_argument("--headless", action="store_true")
ap.add_argument("--max-steps", type=int, default=40)
ap.add_argument("--max-minutes", type=float, default=20)
ap.add_argument("--start")
args = ap.parse_args()

OUT = ROOT / "runs" / args.name
OUT.mkdir(parents=True, exist_ok=True)
LOG = open(OUT / "steps.jsonl", "w")


class Abort(Exception):
    pass


def _text_of(msg):
    c = msg["content"]
    if isinstance(c, str):
        return c
    out = []
    for b in c:
        if b.get("type") == "text":
            out.append(b["text"])
        elif b.get("type") == "tool_result":
            out += [x.get("text", "") for x in b.get("content", []) if x.get("type") == "text"]
    return "\n".join(out)


class LoggingClient(LLMClient):
    def __init__(self):
        super().__init__()
        self.n = 0
        self.warnings_in_row = 0

    async def step(self, system, messages, tools, **kw):
        self.n += 1
        obs = _text_of(messages[-1])
        if "this page shows a CAPTCHA" in obs:
            raise Abort("captcha/bot check detected")
        self.warnings_in_row = self.warnings_in_row + 1 if "WARNING: you have made" in obs else 0
        if self.warnings_in_row >= 3:
            raise Abort("stuck: 3 repeat warnings in a row")
        t = time.monotonic()
        r = await super().step(system, messages, tools, **kw)
        LOG.write(json.dumps({
            "call": self.n,
            "ts": time.strftime("%H:%M:%S"),
            "latency": round(time.monotonic() - t, 1),
            "in_tok": r.usage.input_tokens,
            "out_tok": r.usage.output_tokens,
            "observation": obs,
            "response": [b.model_dump() for b in r.content],
        }, ensure_ascii=False) + "\n")
        LOG.flush()
        return r


async def ask(q):
    if any(w in q.lower() for w in ("captcha", "капч", "робот", "robot", " ip", "ограничен")):
        raise Abort(f"ask_user about bot check: {q}")
    LOG.write(json.dumps({"ask_user": q}, ensure_ascii=False) + "\n")
    return "Пользователь недоступен. Реши сам на своё усмотрение и продолжай."


async def main():
    result = {"name": args.name, "task": args.task}
    t0 = time.monotonic()
    async with BrowserController(headless=args.headless, user_data_dir=str(ROOT / ".agent_profile")) as ctrl:
        if args.start:
            await ctrl.goto(args.start)
        client = LoggingClient()
        loop = AgentLoop(ctrl.page, client=client, max_steps=args.max_steps, ask_user=ask)

        async def on_step(e):
            print(f"{e.step:>2} {time.strftime('%H:%M:%S')} {e.tool_name}({json.dumps(e.tool_input, ensure_ascii=False)[:150]})"
                  f" -> {(e.tool_output or '')[:150]!r}", flush=True)
            try:
                await loop.page.screenshot(path=str(OUT / f"step{e.step:02}.png"))
            except Exception:
                pass

        try:
            r = await asyncio.wait_for(loop.run(args.task, on_step=on_step), args.max_minutes * 60)
            result.update(status="finished", success=r.success, steps=r.steps, summary=r.summary)
        except Abort as exc:
            result.update(status="aborted", reason=str(exc))
            try:  # what tripped the captcha heuristic, for false-positive hunting
                result["captcha_debug"] = await loop.page.evaluate(
                    "({frames: [...document.querySelectorAll('iframe')].map(f => [f.src.slice(0, 120), "
                    "Math.round(f.getBoundingClientRect().width), Math.round(f.getBoundingClientRect().height)]), "
                    "text: (document.title + ' ' + (document.body?.innerText || '').slice(0, 3000)).match("
                    "/captcha|капч|не робот|not a robot|доступ ограничен|подтвердите, что вы|проблема с IP|"
                    "не так с IP|много запросов|too many requests/ig)})"
                )
            except Exception:
                pass
        except asyncio.TimeoutError:
            result.update(status="aborted", reason="wall-clock timeout")
        except Exception as exc:  # noqa: BLE001
            result.update(status="crashed", reason=repr(exc))
        try:
            await loop.page.screenshot(path=str(OUT / "final.png"))
            result["final_url"] = loop.page.url
        except Exception:
            pass
        result.update(notes=loop.notes, minutes=round((time.monotonic() - t0) / 60, 1), llm_calls=client.n)
    (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print("\nRESULT", json.dumps(result, ensure_ascii=False, indent=1))


asyncio.run(main())

"""Summarize a run from runs/<NAME>/: steps (tool, short input/output, reasoning) and result.

usage: python scripts/run_report.py NAME [full]
"""
import json, sys
from pathlib import Path
run = Path(__file__).resolve().parent.parent / "runs" / sys.argv[1]
full = len(sys.argv) > 2
for line in open(run / "steps.jsonl"):
    d = json.loads(line)
    if "call" not in d:
        print("  ", d); continue
    tool = next((b for b in d["response"] if b.get("type") == "tool_use"), None)
    text = " ".join(b.get("text", "") for b in d["response"] if b.get("type") == "text").strip()
    obs_head = d["observation"].split("\n", 1)[0][:110]
    print(f"{d['call']:>2} in={d['in_tok']:>5} {d['latency']:>5}s  <- {obs_head}")
    if text: print(f"     think: {text[:300 if not full else 3000]}")
    if tool: print(f"     {tool['name']}({json.dumps(tool['input'], ensure_ascii=False)[:200 if not full else 3000]})")
r = json.loads((run / "result.json").read_text())
print("\nRESULT:", r.get("status"), r.get("success"), r.get("steps"), r.get("minutes"), "min", r.get("reason", ""))
print(r.get("summary", "")[:3000])

"""Scenario harness: a business using the platform, step by step.

Every step is recorded with one of four outcomes:

  PASS  the platform did what the specification says
  FAIL  it did not: a refusal that should not happen, an acceptance that
        should have been refused, a crash, or a cascade that never fired
  GAP   it did what the code says, but a real organisation would be stuck,
        misled, or forced into a workaround
  NOTE  an observation worth recording, neither right nor wrong
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = os.environ.get("SMG_API", "http://localhost:8080/api")
# The published demo password from app/seed.py. The harness runs only against
# a seeded development stack; it refuses nothing and should never meet real data.
PASSWORD = os.environ.get("SMG_DEMO_PASSWORD", "changeme123")
# platform/, where docker-compose.yml lives
PLATFORM = pathlib.Path(__file__).resolve().parents[2]
TODAY = date.today()


def days(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def call(method: str, path: str, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")[:500]}


def sql(statement: str) -> str:
    """Move time or inspect state directly. Used only to simulate the calendar."""
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql",
         "-U", os.environ.get("POSTGRES_USER", "grc"), "-d", os.environ.get("POSTGRES_DB", "grc"),
         "-tA", "-c", statement],
        capture_output=True, text=True,
        cwd=str(PLATFORM),
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return out.stdout.strip()


def msg(body) -> str:
    if not isinstance(body, dict):
        return str(body)[:200]
    parts = [str(body.get(k)) for k in ("invariant", "code", "constraint") if body.get(k)]
    if body.get("message"):
        parts.append(str(body["message"])[:220])
    detail = body.get("detail")
    if isinstance(detail, dict):
        blocking = detail.get("blocking") or detail.get("failed") or []
        if blocking:
            parts.append("blocking=" + ",".join(
                str(b.get("id") if isinstance(b, dict) else b) for b in blocking))
    elif isinstance(detail, list) and detail and isinstance(detail[0], dict) and "loc" in detail[0]:
        parts.append("; ".join(d.get("msg", "") + " @" + ".".join(map(str, d.get("loc", []))) for d in detail[:3]))
    return " | ".join(parts)


class Run:
    def __init__(self):
        self.results: list[dict] = []
        self.tokens: dict[str, str] = {}
        self.users: dict[str, dict] = {}
        self.scenario = ""

    # -- personas ----------------------------------------------------------
    def login_all(self):
        for key, email in {
            "admin": "admin@example.com", "ciso": "ciso@example.com",
            "analyst": "analyst@example.com", "grc": "grc@example.com",
            "owner": "owner@example.com", "control": "control@example.com",
            "delivery": "delivery@example.com", "appsec": "appsec@example.com",
            "sysowner": "sysowner@example.com", "policy": "policy@example.com",
        }.items():
            s, b = call("POST", "/auth/login", {"email": email, "password": PASSWORD})
            assert s == 200, (email, s, b)
            self.tokens[key] = b["token"]
            self.users[key] = b["user"]

    def uid(self, who: str) -> str:
        return self.users[who]["id"]

    # -- recording ---------------------------------------------------------
    def section(self, name: str):
        self.scenario = name
        print("\n" + "=" * 78 + "\n" + name + "\n" + "=" * 78)

    def record(self, outcome: str, step: str, detail: str = ""):
        self.results.append({"scenario": self.scenario, "outcome": outcome,
                             "step": step, "detail": detail})
        print(f"  {outcome:4}  {step}" + (f"\n        {detail}" if detail else ""))

    def check(self, step: str, ok: bool, detail: str = "") -> bool:
        self.record("PASS" if ok else "FAIL", step, "" if ok else detail)
        return ok

    def gap(self, step: str, detail: str = ""):
        self.record("GAP", step, detail)

    def note(self, step: str, detail: str = ""):
        self.record("NOTE", step, detail)

    # -- calls with expectations ------------------------------------------
    def do(self, who: str, method: str, path: str, body=None, expect=(200, 201),
           step: str | None = None):
        """Make a call that is expected to succeed. Records a FAIL if it does not."""
        s, b = call(method, path, body, self.tokens[who])
        expect = (expect,) if isinstance(expect, int) else expect
        if step:
            self.check(step, s in expect, f"{s} {msg(b)}")
        elif s not in expect:
            self.record("FAIL", f"{method} {path} as {who}", f"{s} {msg(b)}")
        return s, b

    def refused(self, who: str, method: str, path: str, body, step: str, rule: str | None = None):
        """A call that the rules should refuse. PASS only if refused, and by the named rule."""
        s, b = call(method, path, body, self.tokens[who])
        named = msg(b)
        ok = s in (400, 403, 409, 422) and (rule is None or rule in named)
        self.check(step, ok, f"{s} {named}")
        return s, b

    def transition(self, who: str, path: str, target: str, step: str | None = None, **extra):
        body = {"target": target, **extra}
        return self.do(who, "POST", path + "/transition", body,
                       step=step or f"{path.split('/')[1]} -> {target}")

    def get(self, who: str, path: str):
        s, b = call("GET", path, None, self.tokens[who])
        if s != 200:
            self.record("FAIL", f"GET {path}", f"{s} {msg(b)}")
        return b

    # -- output ------------------------------------------------------------
    def summary(self, path: str):
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
        print("\n" + "=" * 78)
        print("  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
        for r in self.results:
            if r["outcome"] in ("FAIL", "GAP"):
                print(f"  {r['outcome']:4} [{r['scenario']}] {r['step']}\n         {r['detail']}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=1)
        return counts.get("FAIL", 0) + counts.get("HARN", 0)


def idof(body) -> str | None:
    if not isinstance(body, dict):
        return None
    if "id" in body:
        return body["id"]
    for k in ("objective", "activity", "deployment", "risk", "policy", "treatment",
              "model", "scenario", "exception", "asset", "component"):
        if isinstance(body.get(k), dict) and "id" in body[k]:
            return body[k]["id"]
    return None


def state_of(body) -> str | None:
    if not isinstance(body, dict):
        return None
    for k in ("lifecycle_state", "status", "deployment_status", "state"):
        if k in body:
            return body[k]
    for k in ("objective", "activity", "deployment", "risk", "policy", "treatment",
              "model", "exception"):
        if isinstance(body.get(k), dict):
            return state_of(body[k])
    return None

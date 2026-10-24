#!/usr/bin/env python3
"""Read or extend the expense tracker's Firebase data (node: expenses-data).

  fb.py show                     counts + HKD settlement per session
  fb.py add new.json [--apply]   merge new expenses/sessions by id (dry run unless --apply)

new.json: {"sessions": [...optional...], "expenses": [{...}]}
Needs FIREBASE_DB_URL in the environment (never commit that URL: the rules are open).
Writes use an ETag precondition, so a change made in the app meanwhile aborts the write.
A backup of the data is saved to $FB_BACKUP_DIR (default /tmp) before every write.
"""
import json, os, sys, time, urllib.error, urllib.request

BASE = os.environ.get("FIREBASE_DB_URL", "").rstrip("/")
if not BASE:
    sys.exit("Set FIREBASE_DB_URL first")
NODE = BASE + "/expenses-data.json"
PEOPLE = ("matt", "vienna")


def as_list(x):
    if x is None:
        return []
    return list(x.values()) if isinstance(x, dict) else [i for i in x if i is not None]


def fetch():
    req = urllib.request.Request(NODE, headers={"X-Firebase-ETag": "true"})
    with urllib.request.urlopen(req, timeout=30) as r:
        etag, data = r.headers.get("ETag"), json.load(r)
    data = data or {}
    return {"sessions": as_list(data.get("sessions")), "expenses": as_list(data.get("expenses"))}, etag


def rates_of(expenses):
    sums = {}
    for e in expenses:
        if e["currency"] != "HKD" and e.get("hkd", 0) > 0 and e["amount"] > 0:
            s = sums.setdefault(e["currency"], [0.0, 0.0]); s[0] += e["hkd"]; s[1] += e["amount"]
    r = {c: a / b for c, (a, b) in sums.items()}; r["HKD"] = 1.0
    return r


def settlement(expenses, session_ids):
    """Same maths as the app. balance > 0 means Vienna owes Matt (HKD)."""
    rates = rates_of(expenses)
    out = {"matt_paid": 0.0, "vienna_paid": 0.0, "matt_share": 0.0, "estimated": 0.0, "missing": 0}
    for e in expenses:
        if e["sessionId"] not in session_ids:
            continue
        if e["currency"] == "HKD":
            v, est = e["amount"], False
        elif e.get("hkd", 0) > 0:
            v, est = e["hkd"], False
        elif e["currency"] in rates:
            v, est = e["amount"] * rates[e["currency"]], True
        else:
            out["missing"] += 1; continue
        pct = 100 if e["forWhom"] == "matt" else 0 if e["forWhom"] == "vienna" else e.get("splitRatio", 50)
        share = v * pct / 100
        out["matt_paid" if e["paidBy"] == "matt" else "vienna_paid"] += v
        out["matt_share"] += share
        if est:
            out["estimated"] += (v if e["paidBy"] == "matt" else 0) - share
    out["balance"] = out["matt_paid"] - out["matt_share"]
    out["rates"] = rates
    return out


def show():
    data, _ = fetch()
    print(f"{len(data['sessions'])} sessions, {len(data['expenses'])} expenses")
    for s in data["sessions"]:
        n = sum(1 for e in data["expenses"] if e["sessionId"] == s["id"])
        r = settlement(data["expenses"], {s["id"]})
        who = "Vienna pays Matt" if r["balance"] > 0 else "Matt pays Vienna"
        print(f"  {s['id']:<10} {s['name']:<18} {n:>3} expenses   {who} HK${abs(r['balance']):,.2f}"
              f"  (estimated part HK${abs(r['estimated']):,.2f})")
    r = settlement(data["expenses"], {s["id"] for s in data["sessions"] if not s.get("settled")})
    print(f"  all open sessions: HK${r['balance']:,.2f}  rates: "
          + ", ".join(f"{c}={v:.5f}" for c, v in r["rates"].items() if c != "HKD"))


def validate(e, session_ids):
    errs = []
    for k in ("id", "sessionId", "amount", "currency", "date", "paidBy", "forWhom", "category"):
        if k not in e:
            errs.append(f"missing {k}")
    if errs:
        return errs
    if e["sessionId"] not in session_ids: errs.append("unknown sessionId")
    if not isinstance(e["amount"], (int, float)) or e["amount"] <= 0: errs.append("bad amount")
    if e["paidBy"] not in PEOPLE: errs.append("bad paidBy")
    if e["forWhom"] not in PEOPLE + ("both",): errs.append("bad forWhom")
    if "hkd" in e and (not isinstance(e["hkd"], (int, float)) or e["hkd"] <= 0): errs.append("bad hkd")
    return errs


def add(path, apply):
    new = json.load(open(path))
    data, etag = fetch()
    have_s = {s["id"] for s in data["sessions"]}
    have_e = {e["id"] for e in data["expenses"]}
    sessions = [s for s in new.get("sessions", []) if s["id"] not in have_s]
    all_s = have_s | {s["id"] for s in sessions}
    added, problems = [], []
    for e in new.get("expenses", []):
        e = dict(e)
        e.setdefault("splitRatio", 50)
        e.setdefault("createdAt", int(time.time() * 1000))
        if e.get("id") in have_e:
            problems.append(f"{e['id']}: already exists, skipped"); continue
        errs = validate(e, all_s)
        if errs:
            problems.append(f"{e.get('id')}: {', '.join(errs)}"); continue
        if e["paidBy"] == e["forWhom"]:
            problems.append(f"{e['id']}: paid and used by the same person, no settlement effect (added anyway)")
        added.append(e)
    before = settlement(data["expenses"], all_s)["balance"]
    merged = data["expenses"] + added
    after = settlement(merged, all_s)["balance"]
    print(f"adding {len(sessions)} sessions, {len(added)} expenses")
    for p in problems: print("  note:", p)
    print(f"HKD balance (Vienna owes Matt): {before:,.2f} -> {after:,.2f}")
    if not apply:
        print("dry run only; re-run with --apply to write"); return
    backup = os.path.join(os.environ.get("FB_BACKUP_DIR", "/tmp"), f"fb-backup-{int(time.time())}.json")
    json.dump(data, open(backup, "w"), ensure_ascii=False)
    body = json.dumps({"sessions": data["sessions"] + sessions, "expenses": merged,
                       "lastUpdated": int(time.time() * 1000)}, ensure_ascii=False).encode()
    req = urllib.request.Request(NODE, data=body, method="PUT",
                                 headers={"Content-Type": "application/json", "if-match": etag})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as ex:
        sys.exit("conflict: data changed while preparing, re-run" if ex.code == 412 else f"write failed: {ex}")
    print(f"written. backup: {backup}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["show"]: show()
    elif a[:1] == ["add"] and len(a) >= 2: add(a[1], "--apply" in a)
    else: print(__doc__)

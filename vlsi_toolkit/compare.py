"""Compare two runs: regression vs regression, timing report vs timing report.

Regression: tests are matched by name (seeds usually differ between runs). A
test counts as failing if any of its seeds failed. Result groups:
  new_failures   passed before, fails now          <- look at these first
  fixed          failed before, passes now
  still_failing  failed in both runs (signature changes are reported)
  added/removed  tests that exist in only one run

Timing: compares WNS/TNS per check and, per endpoint, the worst slack:
  new_violations / fixed / degraded / improved (beyond a small tolerance)
"""

from .regress import signatures


def _by_test(results):
    tests = {}
    for r in results:
        t = tests.setdefault(
            r.test, {"status": "PASS", "seeds": [], "signature": "", "errors": 0}
        )
        t["seeds"].append(r.seed)
        t["errors"] += r.errors + r.fatals
        if r.status != "PASS":
            # FAIL beats INCOMPLETE beats PASS
            if t["status"] == "PASS" or (
                t["status"] == "INCOMPLETE" and r.status == "FAIL"
            ):
                t["status"] = r.status
                t["signature"] = r.signature
    return tests


def compare_regressions(old_results, new_results):
    old, new = _by_test(old_results), _by_test(new_results)
    rows = []
    for name in sorted(set(old) | set(new)):
        o, n = old.get(name), new.get(name)
        if o is None:
            change = "added"
        elif n is None:
            change = "removed"
        elif o["status"] == "PASS" and n["status"] != "PASS":
            change = "new_failure"
        elif o["status"] != "PASS" and n["status"] == "PASS":
            change = "fixed"
        elif o["status"] != "PASS" and n["status"] != "PASS":
            change = "still_failing"
        else:
            change = "still_passing"
        rows.append(
            {
                "test": name,
                "change": change,
                "old_status": o["status"] if o else None,
                "new_status": n["status"] if n else None,
                "old_signature": o["signature"] if o else "",
                "new_signature": n["signature"] if n else "",
                "signature_changed": bool(
                    o
                    and n
                    and o["signature"] != n["signature"]
                    and change == "still_failing"
                ),
            }
        )

    def rate(res):
        return sum(r.status == "PASS" for r in res) / len(res) if res else 0.0

    old_sigs, new_sigs = set(signatures(old_results)), set(signatures(new_results))
    count = {
        c: sum(r["change"] == c for r in rows)
        for c in (
            "new_failure",
            "fixed",
            "still_failing",
            "still_passing",
            "added",
            "removed",
        )
    }
    return {
        "old": {
            "logs": len(old_results),
            "tests": len(old),
            "pass_rate": rate(old_results),
        },
        "new": {
            "logs": len(new_results),
            "tests": len(new),
            "pass_rate": rate(new_results),
        },
        "counts": count,
        "rows": rows,
        "new_signatures": sorted(new_sigs - old_sigs),
        "gone_signatures": sorted(old_sigs - new_sigs),
        "verdict": (
            "regressed"
            if count["new_failure"]
            else "improved" if count["fixed"] else "unchanged"
        ),
    }


def _endpoint_worst(paths):
    worst = {}
    for p in paths:
        if p.slack is None:
            continue
        key = (p.check, p.endpoint)
        if key not in worst or p.slack < worst[key]:
            worst[key] = p.slack
    return worst


def compare_timing(old_paths, new_paths, tolerance=0.005):
    """tolerance (ns): slack changes smaller than this count as unchanged."""
    from .timing_report import summarize

    so, sn = summarize(old_paths), summarize(new_paths)
    checks = []
    for c in sorted(set(so) | set(sn), key=lambda c: c != "setup"):
        o, n = so.get(c, {}), sn.get(c, {})
        checks.append(
            {
                "check": c,
                "old_wns": o.get("wns"),
                "new_wns": n.get("wns"),
                "old_tns": o.get("tns", 0.0),
                "new_tns": n.get("tns", 0.0),
                "old_violations": o.get("violations", 0),
                "new_violations": n.get("violations", 0),
                "delta_wns": (
                    round(n["wns"] - o["wns"], 4)
                    if o.get("wns") is not None and n.get("wns") is not None
                    else None
                ),
                "delta_tns": round(n.get("tns", 0.0) - o.get("tns", 0.0), 4),
            }
        )

    wo, wn = _endpoint_worst(old_paths), _endpoint_worst(new_paths)
    rows = []
    for key in sorted(set(wo) | set(wn)):
        a, b = wo.get(key), wn.get(key)
        if a is None:
            change = "new_violation" if b < 0 else "added"
        elif b is None:
            change = "removed"
        elif a < 0 <= b:
            change = "fixed"
        elif b < 0 <= a:
            change = "new_violation"
        elif b - a > tolerance:
            change = "improved"
        elif a - b > tolerance:
            change = "degraded"
        else:
            change = "unchanged"
        rows.append(
            {
                "check": key[0],
                "endpoint": key[1],
                "old_slack": a,
                "new_slack": b,
                "delta": round(b - a, 4) if a is not None and b is not None else None,
                "change": change,
            }
        )
    count = {
        c: sum(r["change"] == c for r in rows)
        for c in (
            "new_violation",
            "fixed",
            "degraded",
            "improved",
            "unchanged",
            "added",
            "removed",
        )
    }
    worse = count["new_violation"] or any(
        (c["delta_wns"] or 0) < -tolerance for c in checks
    )
    better = count["fixed"] or any((c["delta_wns"] or 0) > tolerance for c in checks)
    return {
        "checks": checks,
        "rows": rows,
        "counts": count,
        "verdict": (
            "regressed"
            if worse and not better
            else (
                "improved"
                if better and not worse
                else "mixed" if worse and better else "unchanged"
            )
        ),
    }

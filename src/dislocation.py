"""Rate-change dislocation analysis: SQL + Python.

Rates 120,000 synthetic policies under clean v1 and clean v2 tables, loads
them into SQLite, and runs the analytical queries in
``sql/dislocation_analysis.sql``: min/max/avg premium change by state, breed
group and age band, plus renewal capping-rule logic (increases capped at
+15%, decreases floored at -10%) with the capped book re-computed.

ALL DATA IN THIS REPOSITORY IS SYNTHETIC.
"""

from __future__ import annotations

import os
import sqlite3

import pandas as pd

import rate_manual
from data_gen import generate_policies
from rating_engine import RatingEngine

INCREASE_CAP = 0.15
DECREASE_FLOOR = -0.10


def _load_sql_queries(sql_path: str) -> list[tuple[str, str]]:
    """Split the .sql file into (name, sql) queries on '-- name: ...' markers."""
    with open(sql_path, encoding="utf-8") as fh:
        text = fh.read()
    queries: list[tuple[str, str]] = []
    name, buf = None, []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("-- name:"):
            if name is not None:
                queries.append((name, "\n".join(buf)))
            name = stripped.split("-- name:")[1].strip()
            buf = []
        elif not stripped.startswith("--"):
            buf.append(line)
    if name is not None:
        queries.append((name, "\n".join(buf)))
    return [(n, q) for n, q in queries if q.strip()]


def run_dislocation(clean_root: str, sql_path: str,
                    n_policies: int = 120_000, seed: int = 20261013) -> dict:
    """Rate policies under v1/v2, run SQL analysis, return result frames."""
    policies = generate_policies(n_policies, seed)
    eng_v1 = RatingEngine(os.path.join(clean_root, "v1"), "v1")
    eng_v2 = RatingEngine(os.path.join(clean_root, "v2"), "v2")

    rows = []
    for p in policies:
        r1 = eng_v1.calculate_premium(p)
        r2 = eng_v2.calculate_premium(p)
        assert not r1["unrated"] and not r2["unrated"], "clean tables must rate every policy"
        band = rate_manual.resolve_age_band(p["pet_age_years"], "v1")["band_label"]
        rows.append({
            "policy_id": p["policy_id"],
            "state": p["state"],
            "territory": p["territory"],
            "breed_group": p["breed_group"],
            "age_band": band,
            "plan": p["plan"],
            "deductible": p["deductible"],
            "v1_cents": r1["premium_cents"],
            "v2_cents": r2["premium_cents"],
        })
    frame = pd.DataFrame(rows)

    con = sqlite3.connect(":memory:")
    frame.to_sql("policies", con, index=False)
    results = {}
    with open(sql_path, encoding="utf-8") as fh:
        script = fh.read()
    # Run DDL (CREATE VIEW) once, then the named SELECT queries.
    con.executescript(
        "\n".join(line for line in script.splitlines()
                  if not line.strip().startswith("-- name:")))
    for name, sql in _load_sql_queries(sql_path):
        results[name] = pd.read_sql_query(sql, con)
    con.close()

    results["n_policies"] = len(frame)
    results["policies"] = frame
    return results

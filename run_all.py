#!/usr/bin/env python3
"""End-to-end pipeline: build tables, validate, analyze dislocation, monitor.

  1. Builds clean v1/v2 rate tables and the 23-defect v2 tables (+ manifest).
  2. Runs the pre-deployment validation suite (50,000 quotes x v1 clean,
     v2 clean, v2 defective) against the reference rate manual.
  3. Runs the dislocation analysis on 120,000 policies (SQL + Python) and
     exports the Excel summary workbook.
  4. Simulates 72h of live rating events with 3 seeded anomalies and runs
     the post-deployment monitor.

All outputs land in outputs/. ALL DATA IS SYNTHETIC.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from data_gen import generate_quotes
from defect_injection import build_all
from dislocation import run_dislocation
from excel_export import build_workbook
from monitor import run_monitor, simulate_events, write_outputs as write_monitor_outputs
from rating_engine import RatingEngine
from validate_rates import attribute_defects, run_validation_suite, write_report

ROOT = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(ROOT, "data", "rate_tables")
OUT = os.path.join(ROOT, "outputs")
SQL = os.path.join(ROOT, "sql", "dislocation_analysis.sql")

N_QUOTES = 50_000
N_POLICIES = 120_000


def main() -> dict:
    os.makedirs(OUT, exist_ok=True)

    # 1. tables + defects ------------------------------------------------------
    built = build_all(TABLES, os.path.join(OUT, "defect_manifest.json"))
    manifest = built["manifest"]

    # 2. validation ------------------------------------------------------------
    quotes = generate_quotes(N_QUOTES)
    suite_results = {}
    for version, table_dir in [("v1", f"{TABLES}/clean/v1"),
                               ("v2", f"{TABLES}/clean/v2")]:
        engine = RatingEngine(table_dir, version)
        report = run_validation_suite(engine, version, quotes)
        attribution = attribute_defects(report, [])
        write_report(report, attribution,
                     os.path.join(OUT, f"validation_report_{version}_clean.json"))
        suite_results[f"{version}_clean"] = {
            "quotes": report["quotes_tested"],
            "mismatches": report["mismatches"],
            "match_rate": report["match_rate"],
        }

    engine_def = RatingEngine(f"{TABLES}/defective/v2", "v2")
    report_def = run_validation_suite(engine_def, "v2", quotes)
    attribution = attribute_defects(report_def, manifest)
    write_report(report_def, attribution,
                 os.path.join(OUT, "validation_report_v2_defective.json"))
    suite_results["v2_defective"] = {
        "quotes": report_def["quotes_tested"],
        "mismatches": report_def["mismatches"],
        "defects_caught": sum(1 for d in attribution if d["caught"]),
        "defects_total": len(attribution),
    }

    # 3. dislocation ------------------------------------------------------------
    dis = run_dislocation(f"{TABLES}/clean", SQL, N_POLICIES)
    build_workbook(dis, os.path.join(OUT, "rate_change_dislocation_summary.xlsx"))
    for name in ("overall", "by_state", "by_breed", "by_age_band",
                 "capping", "cap_hit_by_state"):
        dis[name].to_csv(os.path.join(OUT, f"dislocation_{name}.csv"), index=False)
    overall = dis["overall"].iloc[0]
    capping = dis["capping"].iloc[0]
    dislocation_summary = {
        "n_policies": int(overall["n_policies"]),
        "min_change_pct": float(overall["min_change_pct"]),
        "avg_change_pct": float(overall["avg_change_pct"]),
        "max_change_pct": float(overall["max_change_pct"]),
        "capped_increases": int(capping["capped_increases"]),
        "capped_decreases": int(capping["capped_decreases"]),
        "avg_capped_change_pct": float(capping["avg_capped_change_pct"]),
    }

    # 4. monitoring ---------------------------------------------------------------
    events, zip_map = simulate_events(f"{TABLES}/clean")
    mon = run_monitor(events, zip_map)
    write_monitor_outputs(mon, os.path.join(OUT, "monitoring_alerts.json"),
                          os.path.join(OUT, "monitoring_hourly_metrics.csv"))
    monitoring_summary = {
        "n_events": mon["n_events"],
        "anomalies_seeded": mon["anomalies_seeded"],
        "anomalies_detected": mon["anomalies_detected"],
        "all_within_24h": mon["all_within_24h"],
        "alerts": [
            {"kind": a["kind"],
             "latency_hours": a["detection_latency_hours"]} for a in mon["alerts"]
        ],
    }

    summary = {
        "validation": suite_results,
        "dislocation": dislocation_summary,
        "monitoring": monitoring_summary,
    }
    with open(os.path.join(OUT, "run_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()

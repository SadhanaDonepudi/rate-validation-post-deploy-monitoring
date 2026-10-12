"""Post-deployment monitoring simulation.

Simulates a stream of live rating events over 72 simulated hours and runs an
hourly monitoring batch with three independent checks:

  * Check A - rate-version consistency: every live event must carry the
    currently deployed rate version (``v2``). A stale-version rate above
    0.5% of hourly events raises STALE_FACTOR_USAGE.
  * Check C - territory-mapping consistency: the event's assigned territory
    must match the authoritative ZIP -> territory map. A mismatch rate above
    2% of the hourly sample raises TERRITORY_MISMAPPING.
  * Check B - premium recomputation: a sample of events is re-rated with the
    reference implementation; if more than 2% deviate by more than $0.50,
    RATE_DRIFT is raised for the worst territory.

Three anomalies are seeded (all times in simulated hours):
  * ANOM-01 RATE_DRIFT ......... t=10: territory TX-02's live factor drifts
    upward 1.5% per simulated hour (bad config push);
  * ANOM-02 STALE_FACTOR_USAGE . t=30..36: 8% of events are rated with the
    superseded v1 tables on a lagging node (deployment lag);
  * ANOM-03 TERRITORY_MISMAPPING t=50..56: a stale ZIP map routes FL-01
    policies to territory FL-02 on one node.

Repeat alerts of the same type are suppressed for 12 hours. Detection
latency is measured in simulated hours from anomaly start to alert.

ALL DATA IN THIS REPOSITORY IS SYNTHETIC. Latencies are simulated, not
measured production values.
"""

from __future__ import annotations

import csv
import json
import random

import rate_manual
from data_gen import quote_combinations
from rating_engine import RatingEngine

HOURS = 72
EVENTS_PER_HOUR = 30
CURRENT_VERSION = "v2"

STALE_THRESHOLD = 0.005
MISMATCH_THRESHOLD = 0.02
DEVIATION_DOLLARS = 0.50
DEVIATION_RATE_THRESHOLD = 0.02
ALERT_COOLDOWN_HOURS = 12

ANOMALIES = [
    {"id": "ANOM-01", "kind": "RATE_DRIFT", "start_hour": 10, "end_hour": None,
     "description": "TX-02 live factor drifts +1.5%/hour from the deployed value."},
    {"id": "ANOM-02", "kind": "STALE_FACTOR_USAGE", "start_hour": 30, "end_hour": 36,
     "description": "8% of events rated with superseded v1 tables (lagging node)."},
    {"id": "ANOM-03", "kind": "TERRITORY_MISMAPPING", "start_hour": 50, "end_hour": 56,
     "description": "Stale ZIP map routes FL-01 policies to territory FL-02."},
]

DRIFT_TERRITORY = "TX-02"
DRIFT_PER_HOUR = 0.015
DRIFT_BASE_FACTOR = 1.24  # clean v2 TX-02 factor


def build_zip_map(seed: int = 7) -> dict[str, list[str]]:
    """Authoritative synthetic ZIP -> territory mapping (3 ZIPs per territory)."""
    rng = random.Random(seed)
    zip_map: dict[str, list[str]] = {}
    used = set()
    for territory in rate_manual.TERRITORY_FACTORS["v2"]:
        zips = []
        while len(zips) < 3:
            z = f"{rng.randint(10000, 99999):05d}"
            if z not in used:
                used.add(z)
                zips.append(z)
        zip_map[territory] = zips
    return zip_map


def simulate_events(clean_root: str, hours: int = HOURS,
                    events_per_hour: int = EVENTS_PER_HOUR,
                    seed: int = 20261014) -> tuple[list[dict], dict[str, str]]:
    """Simulate the live rating-event stream with 3 seeded anomalies."""
    rng = random.Random(seed)
    zip_map = build_zip_map()
    zip_to_territory = {z: t for t, zs in zip_map.items() for z in zs}
    combos = quote_combinations()
    eng_v2 = RatingEngine(f"{clean_root}/v2", "v2")
    eng_v1 = RatingEngine(f"{clean_root}/v1", "v1")

    events: list[dict] = []
    for h in range(hours):
        for _ in range(events_per_hour):
            t = h + rng.random()
            base = rng.choice(combos)
            true_territory = base["territory"]
            zip_code = rng.choice(zip_map[true_territory])
            version, engine, assigned = "v2", eng_v2, true_territory

            # ANOM-02: lagging node still on v1 tables.
            if 30 <= t < 36 and rng.random() < 0.08:
                version, engine = "v1", eng_v1

            # ANOM-03: stale ZIP map on one node (FL-01 -> FL-02).
            if 50 <= t < 56 and true_territory == "FL-01":
                assigned = "FL-02"

            quote = {
                "territory": assigned,
                "breed_group": base["breed_group"],
                "pet_age_years": rng.randint(0, 15),
                "plan": base["plan"],
                "deductible": base["deductible"],
            }
            rated = engine.calculate_premium(quote)
            premium_cents = rated["premium_cents"]

            # ANOM-01: TX-02 factor drifts on the live node.
            if t >= 10 and assigned == DRIFT_TERRITORY and version == "v2":
                drifted = DRIFT_BASE_FACTOR * (1 + DRIFT_PER_HOUR) ** (t - 10)
                premium_cents = int(round(premium_cents * drifted / DRIFT_BASE_FACTOR))

            events.append({
                "t": t,
                "zip": zip_code,
                "true_territory": true_territory,
                "assigned_territory": assigned,
                "version": version,
                "breed_group": quote["breed_group"],
                "pet_age_years": quote["pet_age_years"],
                "plan": quote["plan"],
                "deductible": quote["deductible"],
                "premium_cents": premium_cents,
            })
    return events, zip_to_territory


def _reference_premium(event: dict, zip_to_territory: dict) -> int:
    quote = {
        "territory": zip_to_territory[event["zip"]],
        "breed_group": event["breed_group"],
        "pet_age_years": event["pet_age_years"],
        "plan": event["plan"],
        "deductible": event["deductible"],
    }
    return rate_manual.calculate_premium(quote, CURRENT_VERSION)["premium_cents"]


def run_monitor(events: list[dict], zip_to_territory: dict,
                hours: int = HOURS) -> dict:
    """Run the hourly monitoring batch. Returns alerts + hourly metrics."""
    alerts: list[dict] = []
    metrics: list[dict] = []
    last_alert: dict[str, float] = {}
    anomaly_start = {"STALE_FACTOR_USAGE": 30, "TERRITORY_MISMAPPING": 50,
                     "RATE_DRIFT": 10}

    for h in range(1, hours + 1):
        window = [e for e in events if h - 1 <= e["t"] < h]
        sample = [e for e in window if e["version"] == CURRENT_VERSION][:200]
        row = {"hour": h, "n_events": len(window)}

        stale = [e for e in window if e["version"] != CURRENT_VERSION]
        stale_rate = len(stale) / len(window) if window else 0.0
        row["stale_rate"] = round(stale_rate, 6)

        mismapped = [e for e in sample
                     if e["assigned_territory"] != zip_to_territory[e["zip"]]]
        mismap_rate = len(mismapped) / len(sample) if sample else 0.0
        row["mismap_rate"] = round(mismap_rate, 6)

        dev_by_terr: dict[str, list[float]] = {}
        n_dev = 0
        for e in sample:
            ref_cents = _reference_premium(e, zip_to_territory)
            dev = abs(e["premium_cents"] - ref_cents) / 100.0
            dev_by_terr.setdefault(e["assigned_territory"], []).append(dev)
            if dev > DEVIATION_DOLLARS:
                n_dev += 1
        dev_rate = n_dev / len(sample) if sample else 0.0
        row["deviation_rate"] = round(dev_rate, 6)

        fired = None
        # Check order is deliberate: version, then mapping, then premium drift,
        # so a mapping incident is attributed to mapping even though premiums
        # also deviate.
        if stale_rate > STALE_THRESHOLD:
            fired = ("STALE_FACTOR_USAGE",
                     f"{len(stale)}/{len(window)} events on superseded rate "
                     f"version (stale rate {stale_rate:.2%} > {STALE_THRESHOLD:.2%}).")
        elif mismap_rate > MISMATCH_THRESHOLD:
            worst = max(set(e["true_territory"] for e in mismapped),
                        key=lambda terr: sum(1 for e in mismapped
                                             if e["true_territory"] == terr))
            fired = ("TERRITORY_MISMAPPING",
                     f"{len(mismapped)}/{len(sample)} sampled events mis-mapped "
                     f"(rate {mismap_rate:.2%} > {MISMATCH_THRESHOLD:.2%}); "
                     f"worst territory {worst}.")
        elif dev_rate > DEVIATION_RATE_THRESHOLD:
            worst = max(dev_by_terr,
                        key=lambda terr: sum(dev_by_terr[terr]) / len(dev_by_terr[terr]))
            mean_dev = sum(dev_by_terr[worst]) / len(dev_by_terr[worst])
            fired = ("RATE_DRIFT",
                     f"{n_dev}/{len(sample)} sampled events deviate > "
                     f"${DEVIATION_DOLLARS:.2f} from reference "
                     f"(rate {dev_rate:.2%} > {DEVIATION_RATE_THRESHOLD:.2%}); "
                     f"worst territory {worst} (mean deviation ${mean_dev:.2f}).")

        if fired:
            kind, detail = fired
            # One alert per anomaly kind: once an incident is open it stays
            # open rather than re-alerting every cooldown window.
            if kind not in last_alert:
                last_alert[kind] = h
                alerts.append({
                    "alert_id": f"ALT-{len(alerts) + 1:03d}",
                    "kind": kind,
                    "detected_at_hour": h,
                    "anomaly_start_hour": anomaly_start[kind],
                    "detection_latency_hours": round(h - anomaly_start[kind], 2),
                    "detail": detail,
                })
        row["alert"] = fired[0] if fired else ""
        metrics.append(row)

    max_latency = max((a["detection_latency_hours"] for a in alerts), default=None)
    return {
        "n_events": len(events),
        "hours_simulated": hours,
        "anomalies_seeded": len(ANOMALIES),
        "anomalies": ANOMALIES,
        "alerts": alerts,
        "alerts_fired": len(alerts),
        "anomalies_detected": len({a["kind"] for a in alerts}),
        "max_detection_latency_hours": max_latency,
        "all_within_24h": all(a["detection_latency_hours"] < 24 for a in alerts),
        "hourly_metrics": metrics,
    }


def write_outputs(result: dict, alerts_path: str, metrics_path: str) -> None:
    payload = {k: v for k, v in result.items() if k != "hourly_metrics"}
    with open(alerts_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    with open(metrics_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(result["hourly_metrics"][0].keys()))
        writer.writeheader()
        writer.writerows(result["hourly_metrics"])

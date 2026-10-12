# Corrective-Redeployment Playbook (Post-Deployment Rating Incidents)

> **SYNTHETIC CONTEXT** — this playbook is written against the simulated
> monitoring in this repo. Any time figures below (e.g. *"corrective redeploy
> live within 4 hours of detection"*) are **design targets**, not measured
> production results. The simulation measures detection latency only.

## 1. Detection (automated, hourly batch)

The monitor in `src/monitor.py` runs three checks every simulated hour:

| Check | Signal | Alert threshold | Seeded anomaly it catches |
|---|---|---|---|
| A — version consistency | share of events not on the deployed version | > 0.5% | ANOM-02 stale-factor usage |
| C — territory mapping | share of sampled events whose assigned territory ≠ authoritative ZIP map | > 2% | ANOM-03 territory mis-mapping |
| B — premium recomputation | share of sampled events deviating > $0.50 from the reference re-rating | > 2% | ANOM-01 rate drift |

Check order (A → C → B) attributes an incident to its most specific cause:
a mapping incident also moves premiums, but it is reported as mis-mapping,
not drift. One alert fires per anomaly kind; the incident stays open instead
of re-alerting.

**Measured in simulation:** all 3 seeded anomalies detected, each within
1 simulated hour of injection (requirement: < 24 h).

## 2. Triage (target: within 30 minutes of alert — design target)

1. Open the alert; note `kind`, worst territory, and the hourly-metrics trend
   (`outputs/monitoring_hourly_metrics.csv`).
2. Classify severity:
   - **SEV-1**: premium deviation affecting > 5% of hourly volume, or any
     stale-version usage (wrong prices in production).
   - **SEV-2**: localized drift/mis-mapping under 5% of volume.
3. Estimate blast radius: re-run the validation suite (`run_all.py`) against
   the *live* tables to list every affected (element, key) — the same
   signature grouping used pre-deployment.
4. Decide: **rollback** (restore previous tables) vs **forward-fix**
   (correct the table cell and redeploy). Default to rollback for SEV-1.

## 3. Containment & corrective redeploy (target: live within 4 hours of detection — design target)

1. Freeze the release pipeline for the rating service.
2. Rollback: point the engine at the last validated table build
   (`data/rate_tables/clean/v1`), or forward-fix the defective cells and
   rebuild the tables with `src/defect_injection.py`.
3. **Gate the redeploy on the validation suite**: 50,000 quotes per version
   must reach 100% premium match against the reference manual before the
   tables ship. In this repo's simulation the clean tables achieve exactly
   that (0 mismatches / 50,000 per version).
4. Deploy with the version tag bumped; verify Check A shows 0% stale within
   the next hourly batch.
5. Re-run the dislocation queries to confirm the book moved as intended and
   the capping guardrails (+15% / −10%) hold.

## 4. Verification (post-redeploy)

- Monitor the next 3 hourly batches: stale rate 0%, mis-mapping 0%,
  deviation rate back to baseline.
- Reconcile a sample of affected policies: recompute premiums under the
  corrected tables; confirm remediation amounts where customers were
  over/under-charged.

## 5. Communications template

> **Subject:** [SEV-n] Rating incident — {kind} detected at {hour}
> **Impact:** {n} policies / {territories} affected, premium deviation {range}.
> **Action:** {rollback to v1 tables | forward-fix of cells …} — corrective
> redeploy target: within 4 hours of detection (design target).
> **Verification:** validation suite 100% match on 50k quotes; monitoring
> checks green for 3 consecutive hours.

## 6. Postmortem (within 5 business days — design target)

Record: root cause (which table cell / pipeline step), why pre-deployment
validation missed it (add a regression quote set), time-to-detect vs the
24-hour requirement, and time-to-redeploy vs the 4-hour design target.

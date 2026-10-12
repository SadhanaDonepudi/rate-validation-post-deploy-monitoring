# Pre-Deployment Rate Validation & Post-Deployment Monitoring

> **ALL DATA IN THIS REPOSITORY IS SYNTHETIC** — generated for demonstration.
> No real policyholder, premium, or rate-manual data is used anywhere.

An end-to-end actuarial data-quality workflow for a pet-insurance pricing
release: differentially validate a candidate rate table against an independent
reference implementation of the approved rate manual **before** deployment,
quantify the rate-change dislocation on the in-force book, then monitor the
live rating stream for anomalies **after** deployment.

**Every number below is the actual output of this repo's code** (fixed seeds;
re-run `python3 run_all.py` to reproduce). See [Honesty notes](#honesty-notes).

## Measured results

### 1. Pre-deployment validation — 50,000 synthetic quotes per pricing version

Each quote is rated twice: once by the deployed engine (reading the CSV rate
tables under test) and once by the independent reference implementation of
the approved rate manual; premiums are compared in whole cents.

| Run | Quotes tested | Mismatches | Premium match |
|---|---|---|---|
| v1 clean tables | 50,000 | 0 | **100%** |
| v2 clean tables | 50,000 | 0 | **100%** |
| v2 with 23 planted defects | 50,000 | 50,000 | defects caught **23/23** |

The defective run mismatches on all 50,000 quotes because one planted defect
(DEF-20, base-rate typo) shifts every premium; the suite groups mismatches
into 29 distinct detection signatures and attributes each of the 23 planted
defects individually — wrong factors, mis-keyed territories, off-by-one tiers,
swapped factors, a missing row, a duplicate row, and the base-rate typo
(full catalogue in `outputs/defect_manifest.json`).

### 2. Rate-change dislocation — 120,000 synthetic policies (v1 → v2)

SQL aggregations (`sql/dislocation_analysis.sql` on SQLite) + Python; workbook
at `outputs/rate_change_dislocation_summary.xlsx`.

| Metric | Measured |
|---|---|
| Policies analyzed | 120,000 |
| Min premium change | **−8.97%** |
| Avg premium change | **+2.52%** |
| Max premium change | **+18.11%** |
| Avg v1 → v2 premium | $662.38 → $684.60 |
| Total book premium change | +$2,666,643.86 |

Largest avg increase by state: **CA +4.31%**; by breed group: **BG-15 +6.27%**;
by age band: **10+ +5.56%** (senior factor repriced 1.45 → 1.52). FL averages
−0.17% (FL-02 factor cut 1.28 → 1.22).

Renewal guardrails (+15% increase cap / −10% decrease floor), re-computed:

| Metric | Measured |
|---|---|
| Policies hitting the increase cap | **99** |
| Policies hitting the decrease floor | **0** |
| Avg change after capping | +2.5171% (vs +2.5188% uncapped) |

### 3. Post-deployment monitoring — 72 simulated hours, 2,160 live rating events

Hourly batch with three checks: rate-version consistency, territory-mapping
consistency, and premium recomputation vs the reference.

| Seeded anomaly | Monitor alert | Detection latency |
|---|---|---|
| ANOM-01 rate drift (TX-02 +1.5%/h from t=10) | RATE_DRIFT | **1 simulated hour** |
| ANOM-02 stale v1 factors (8% of events, t=30–36) | STALE_FACTOR_USAGE | **1 simulated hour** |
| ANOM-03 territory mis-mapping (FL-01→FL-02, t=50–56) | TERRITORY_MISMAPPING | **1 simulated hour** |

**3/3 anomalies detected, each within 1 simulated hour** (requirement: < 24 h).
Alerts and hourly metrics: `outputs/monitoring_alerts.json`,
`outputs/monitoring_hourly_metrics.csv`. Incident response is documented in
[`docs/corrective_redeployment_playbook.md`](docs/corrective_redeployment_playbook.md).

## Repository layout

```
├── run_all.py                  # end-to-end pipeline (build → validate → analyze → monitor)
├── src/
│   ├── rate_manual.py          # reference implementation of the approved rate manual
│   ├── rating_engine.py        # deployed engine reading the CSV tables under test
│   ├── data_gen.py             # synthetic quote/policy generators (fixed seeds)
│   ├── defect_injection.py     # builds tables; plants exactly 23 defects + manifest
│   ├── validate_rates.py       # differential validation suite + defect attribution
│   ├── dislocation.py          # dislocation analysis (SQL + Python)
│   ├── monitor.py              # live-event simulation + hourly monitoring batch
│   └── excel_export.py         # formatted Excel summary workbook
├── sql/dislocation_analysis.sql
├── docs/
│   ├── data_dictionary.md
│   ├── corrective_redeployment_playbook.md
│   └── powerbi_dashboard_spec.md   # data model, DAX, page layouts for the monitoring dashboard
├── tests/test_rate_validation.py   # pytest suite (10 tests, ~12 s)
├── data/rate_tables/           # clean v1/v2 + defective v2 CSVs (generated)
└── outputs/                    # reports, workbook, alerts, manifest (generated)
```

## Quickstart

```bash
pip install -r requirements.txt
python3 run_all.py            # builds everything into outputs/
python3 -m pytest tests/ -q  # 10 tests: counts, 100% clean match, 23/23, 120k, 3/3 < 24h
```

## Honesty notes

- **Synthetic data**: quotes, policies, premiums, rate tables, events, ZIPs —
  everything is generated. Nothing here reflects real pricing.
- **100% match on clean tables is by construction**: the reference and the
  engine implement the same published formula (Manual §4.2); the differential
  test validates the *deployed tables*, not the formula. Its power is shown by
  the defective run, where all 23 planted table defects are genuinely detected
  via comparison + boundary/consistency checks, without the suite ever seeing
  the defect manifest.
- **Detection latencies are simulated hours**, not production measurements.
- **"Corrective redeploy live within 4 hours of detection"** in the playbook
  is a **design target**, not a measured result.

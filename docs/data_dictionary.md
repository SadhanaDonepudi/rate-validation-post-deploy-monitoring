# Data Dictionary

> **SYNTHETIC DATA** — every table, quote, policy, and event in this repository
> is generated for demonstration. No real policyholder or pricing data is used.

## Rating dimensions

| Dimension | Values | Notes |
|---|---|---|
| Pricing version | `v1` (in force), `v2` (candidate) | v2 revises 8 rate cells (see below) |
| State | IL, TX, CA, FL, NY, OH, GA, WA | 8 states |
| Territory | 18 codes, e.g. `IL-01`, `TX-02` | 2–3 per state; factor 0.88–1.30 |
| Breed group | `BG-01` … `BG-16` | 16 risk groups; factor 0.82–1.42 |
| Age band | `0-1`, `2-3`, `4-6`, `7-9`, `10+` | Pet age in years; factor 1.00–1.52 |
| Plan | `Comprehensive`, `Accident-only`, `Wellness+` | Factor 0.62–1.22 |
| Deductible | `$250`, `$500`, `$1000` | Factor 0.84–1.12 |
| Base annual premium | $480.00 (v1 and v2) | Single base rate |

### v2 rate revisions (clean v2 vs v1)

| Element | Key | v1 | v2 |
|---|---|---|---|
| Territory | TX-02 | 1.18 | 1.24 |
| Territory | FL-02 | 1.28 | 1.22 |
| Territory | CA-02 | 1.25 | 1.30 |
| Breed | BG-02 | 0.90 | 0.88 |
| Breed | BG-15 | 1.35 | 1.40 |
| Age band | 10+ | 1.45 | 1.52 |
| Plan | Wellness+ | 1.18 | 1.22 |
| Deductible | $1000 | 0.86 | 0.84 |

Rating formula (Manual §4.2): `premium = round(base × territory × breed × age × plan × deductible, 2)`.

## Deployed rate tables (`data/rate_tables/`)

CSV files, one directory per build: `clean/v1`, `clean/v2`, `defective/v2`.

| File | Columns |
|---|---|
| `base_rates.csv` | `version`, `annual_base_premium` |
| `territories.csv` | `version`, `territory_code`, `factor` |
| `breeds.csv` | `version`, `breed_group`, `factor` |
| `age_bands.csv` | `version`, `band_id`, `band_label`, `min_age`, `max_age`, `factor` |
| `plans.csv` | `version`, `plan`, `factor` |
| `deductibles.csv` | `version`, `deductible`, `factor` |

## Validation inputs & outputs

| Artifact | Description |
|---|---|
| Test quote | `quote_id`, `state`, `territory`, `breed_group`, `pet_age_years` (0–15), `plan`, `deductible`. 50,000 per run; full cross-product coverage (12,960 combos) + random extras. |
| `outputs/validation_report_<version>_<build>.json` | `quotes_tested`, `mismatches`, `match_rate`, grouped detection `signatures` (element, key, deployed_value, reference_value, quote_count, example_quotes); defective report also carries the 23-item `defects` attribution. |
| `outputs/defect_manifest.json` | Ground truth for tests only: the 23 planted defects with expected signatures. The suite never reads it. |

## Dislocation analysis

| Artifact | Description |
|---|---|
| Synthetic policy | `policy_id`, `state`, `territory`, `breed_group`, `age_band`, `plan`, `deductible`, `v1_cents`, `v2_cents`. 120,000 policies. |
| `sql/dislocation_analysis.sql` | SQLite queries: overall, by state, by breed group, by age band, capping impact, cap-hit rate by state. |
| `outputs/rate_change_dislocation_summary.xlsx` | Formatted workbook (Cover, Overall, By_State, By_Breed_Group, By_Age_Band, Capping_Impact, Cap_Hit_By_State, Notes). CSV twins: `outputs/dislocation_*.csv`. |

Capping rules: renewal increases capped at **+15%**, decreases floored at **−10%**; capped premium = v1 × (1 + capped change).

## Monitoring simulation

| Field | Description |
|---|---|
| `t` | Simulated event time in hours (0–72) |
| `zip` / `true_territory` / `assigned_territory` | Authoritative ZIP→territory map vs the territory the event was rated with |
| `version` | Rate version tag on the event (`v1`/`v2`) |
| `premium_cents` | Live-rated premium |
| `outputs/monitoring_alerts.json` | Alerts: `kind`, `detected_at_hour`, `detection_latency_hours`, detail |
| `outputs/monitoring_hourly_metrics.csv` | Per-hour `stale_rate`, `mismap_rate`, `deviation_rate`, alert fired |

Seeded anomalies: `ANOM-01` rate drift (TX-02, +1.5%/h from t=10), `ANOM-02` stale v1 factors (8% of events, t=30–36), `ANOM-03` territory mis-mapping (FL-01→FL-02, t=50–56).

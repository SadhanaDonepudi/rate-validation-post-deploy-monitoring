# Power BI Dashboard Spec — Rate Validation & Post-Deployment Monitoring

> **SYNTHETIC DATA** — all tables below are fed by this repo's generators.
> This spec is a build blueprint: data model, relationships, DAX measures,
> and page layouts for the monitoring dashboard.

## 1. Data model

### Fact tables

| Table | Grain | Key columns | Source in repo |
|---|---|---|---|
| `Fact_RatingEvent` | one live rating event | `event_id`, `timestamp`, `zip`, `assigned_territory`, `true_territory`, `rate_version`, `engine_premium`, `expected_premium`, `deviation_amt`, `anomaly_flag` | `src/monitor.py` event stream |
| `Fact_ValidationResult` | one validation run × version | `run_id`, `run_ts`, `rate_version`, `table_build`, `quotes_tested`, `mismatches`, `match_rate`, `defects_caught`, `defects_total` | `outputs/validation_report_*.json` |
| `Fact_ValidationSignature` | one detection signature | `run_id`, `element`, `lookup_key`, `deployed_value`, `reference_value`, `quote_count` | report `signatures` |
| `Fact_Dislocation` | one policy | `policy_id`, `state`, `territory`, `breed_group`, `age_band`, `plan`, `deductible`, `v1_premium`, `v2_premium`, `change_pct`, `capped_premium`, `cap_applied` | `outputs/dislocation_*.csv` |
| `Fact_Alert` | one monitor alert | `alert_id`, `alert_ts`, `kind`, `detection_latency_hrs`, `worst_territory`, `detail` | `outputs/monitoring_alerts.json` |

### Dimension tables

`Dim_Territory` (`territory_code`, `state`, `region`), `Dim_BreedGroup`
(`breed_group`, `risk_tier`), `Dim_AgeBand` (`band_label`, `min_age`, `max_age`),
`Dim_Plan`, `Dim_Deductible`, `Dim_RateVersion` (`version`, `status`),
`Dim_Date` (`date`, `hour`).

### Relationships (single direction, one-to-many)

- `Fact_RatingEvent[assigned_territory]` → `Dim_Territory[territory_code]`
- `Fact_Dislocation[state]` → `Dim_Territory[state]` (via bridge on state) or a
  dedicated `Dim_State`; `Fact_Dislocation[breed_group]` → `Dim_BreedGroup`;
  `Fact_Dislocation[age_band]` → `Dim_AgeBand`
- `Fact_ValidationResult[rate_version]` → `Dim_RateVersion[version]`
- `Fact_RatingEvent[timestamp]` → `Dim_Date[datetime]`; `Fact_Alert[alert_ts]` → `Dim_Date[datetime]`

## 2. DAX measures

```dax
Match Rate % =
DIVIDE ( SUM ( Fact_ValidationResult[quotes_tested] ) - SUM ( Fact_ValidationResult[mismatches] ),
        SUM ( Fact_ValidationResult[quotes_tested] ) )

Defects Caught = SUM ( Fact_ValidationResult[defects_caught] )
Defect Catch Rate % = DIVIDE ( [Defects Caught], SUM ( Fact_ValidationResult[defects_total] ) )

Avg Premium Change % = AVERAGE ( Fact_Dislocation[change_pct] )
Min Premium Change % = MIN ( Fact_Dislocation[change_pct] )
Max Premium Change % = MAX ( Fact_Dislocation[change_pct] )
Cap Hit Rate % =
DIVIDE ( COUNTROWS ( FILTER ( Fact_Dislocation, Fact_Dislocation[cap_applied] = TRUE () ) ),
        COUNTROWS ( Fact_Dislocation ) )

Stale Event Rate % =
DIVIDE ( COUNTROWS ( FILTER ( Fact_RatingEvent, Fact_RatingEvent[rate_version] <> "v2" ) ),
        COUNTROWS ( Fact_RatingEvent ) )

Deviation Rate % =
DIVIDE ( COUNTROWS ( FILTER ( Fact_RatingEvent, ABS ( Fact_RatingEvent[deviation_amt] ) > 0.50 ) ),
        COUNTROWS ( Fact_RatingEvent ) )

Avg Detection Latency (hrs) = AVERAGE ( Fact_Alert[detection_latency_hrs] )
Open Alerts = COUNTROWS ( FILTER ( Fact_Alert, Fact_Alert[status] = "OPEN" ) )
```

## 3. Page layouts

**Page 1 — Executive overview.** KPI cards: Match Rate % (target 100%),
Defect Catch Rate % (23/23), Avg Premium Change %, Cap Hit Rate %, Open
Alerts, Avg Detection Latency. Slicers: rate version, date range.

**Page 2 — Pre-deployment validation.** Table of validation runs (version,
build, quotes, mismatches, match rate); bar chart of detection signatures by
rate element; defect detail table (id, category, element, key, deployed vs
reference value, quotes affected) with drill-through to example quotes.

**Page 3 — Dislocation analysis.** Cards: min/avg/max premium change;
bar charts of avg change by state, breed group, age band; histogram of
`change_pct`; capping panel (policies capped up/down, avg capped vs uncapped
change, premium impact $). Slicers: state, breed group, age band.

**Page 4 — Live monitoring.** Line charts (by hour): stale event rate %,
territory mis-mapping rate %, premium deviation rate % — each with its alert
threshold as a constant line. Alert log table (kind, detected at, latency,
worst territory, detail). Territory heat map of mean deviation.

**Page 5 — Alert response.** Alert cards linked to the corrective-redeployment
playbook (`docs/corrective_redeployment_playbook.md`): triage checklist,
rollback/forward-fix decision, verification steps, comms template.

## 4. Refresh & governance

- `Fact_RatingEvent`: hourly incremental refresh aligned with the monitoring
  batch; `Fact_ValidationResult` / `Fact_Dislocation`: refresh on each release
  candidate.
- Row-level security: restrict `Fact_RatingEvent`/`Fact_Dislocation` to
  authorized actuarial and data-engineering roles (synthetic data here, but
  the model is production-shaped).
- Alerting: Power BI data alerts on `Deviation Rate %` and `Stale Event Rate %`
  mirror the monitor's thresholds.

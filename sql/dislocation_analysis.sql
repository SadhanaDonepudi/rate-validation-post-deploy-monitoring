-- Rate-change dislocation analysis (SQLite).
-- Table `policies` is loaded by src/dislocation.py with one row per synthetic
-- policy: policy_id, state, territory, breed_group, age_band, plan,
-- deductible, v1_cents, v2_cents. ALL DATA IS SYNTHETIC.

-- Base view: per-policy premium change between pricing versions.
CREATE VIEW IF NOT EXISTS policy_changes AS
SELECT policy_id,
       state,
       territory,
       breed_group,
       age_band,
       plan,
       deductible,
       v1_cents,
       v2_cents,
       (v2_cents - v1_cents) * 1.0 / v1_cents AS change_pct
FROM policies;

-- Q1: overall dislocation ----------------------------------------------------
-- name: overall
SELECT COUNT(*)                                   AS n_policies,
       ROUND(MIN(change_pct), 6)                 AS min_change_pct,
       ROUND(AVG(change_pct), 6)                 AS avg_change_pct,
       ROUND(MAX(change_pct), 6)                 AS max_change_pct,
       ROUND(AVG(v1_cents) / 100.0, 2)           AS avg_v1_premium,
       ROUND(AVG(v2_cents) / 100.0, 2)           AS avg_v2_premium,
       ROUND(SUM(v2_cents - v1_cents) / 100.0, 2) AS total_premium_change
FROM policy_changes;

-- Q2: dislocation by state ---------------------------------------------------
-- name: by_state
SELECT state,
       COUNT(*)                   AS n_policies,
       ROUND(MIN(change_pct), 6) AS min_change_pct,
       ROUND(AVG(change_pct), 6) AS avg_change_pct,
       ROUND(MAX(change_pct), 6) AS max_change_pct
FROM policy_changes
GROUP BY state
ORDER BY avg_change_pct DESC;

-- Q3: dislocation by breed group ---------------------------------------------
-- name: by_breed
SELECT breed_group,
       COUNT(*)                   AS n_policies,
       ROUND(MIN(change_pct), 6) AS min_change_pct,
       ROUND(AVG(change_pct), 6) AS avg_change_pct,
       ROUND(MAX(change_pct), 6) AS max_change_pct
FROM policy_changes
GROUP BY breed_group
ORDER BY breed_group;

-- Q4: dislocation by age band ------------------------------------------------
-- name: by_age_band
SELECT age_band,
       COUNT(*)                   AS n_policies,
       ROUND(MIN(change_pct), 6) AS min_change_pct,
       ROUND(AVG(change_pct), 6) AS avg_change_pct,
       ROUND(MAX(change_pct), 6) AS max_change_pct
FROM policy_changes
GROUP BY age_band
ORDER BY age_band;

-- Q5: capping-rule impact -----------------------------------------------------
-- Renewal guardrails: increases capped at +15%, decreases floored at -10%.
-- name: capping
SELECT COUNT(*) AS n_policies,
       SUM(CASE WHEN change_pct >  0.15 THEN 1 ELSE 0 END) AS capped_increases,
       SUM(CASE WHEN change_pct < -0.10 THEN 1 ELSE 0 END) AS capped_decreases,
       ROUND(AVG(CASE WHEN change_pct >  0.15 THEN  0.15
                      WHEN change_pct < -0.10 THEN -0.10
                      ELSE change_pct END), 6)            AS avg_capped_change_pct,
       ROUND(AVG(change_pct), 6)                          AS avg_uncapped_change_pct,
       ROUND(SUM(v1_cents * (1 + CASE WHEN change_pct >  0.15 THEN  0.15
                                     WHEN change_pct < -0.10 THEN -0.10
                                     ELSE change_pct END)) / 100.0, 2)
                                                          AS total_capped_premium,
       ROUND(SUM(v2_cents) / 100.0, 2)                    AS total_uncapped_premium
FROM policy_changes;

-- Q6: distribution of capped vs uncapped changes by state (cap hit rate) ------
-- name: cap_hit_by_state
SELECT state,
       COUNT(*) AS n_policies,
       SUM(CASE WHEN change_pct > 0.15 OR change_pct < -0.10 THEN 1 ELSE 0 END)
           AS capped_policies,
       ROUND(1.0 * SUM(CASE WHEN change_pct > 0.15 OR change_pct < -0.10
                            THEN 1 ELSE 0 END) / COUNT(*), 6) AS cap_hit_rate
FROM policy_changes
GROUP BY state
ORDER BY cap_hit_rate DESC;

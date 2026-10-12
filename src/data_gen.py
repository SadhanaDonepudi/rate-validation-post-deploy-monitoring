"""Synthetic data generators - quotes, policies, and rating inputs.

All data is synthetic. Generation is deterministic given the seed.

Quote coverage strategy for the validation suite: the full cross product of
(territory x breed group x age band x plan x deductible) is enumerated
(43,200 combinations) so that every deployed rate-table cell is exercised at
least once, and the representative pet age cycles through every integer age
inside each band so tier boundaries are exercised. The remaining quotes are
random extras.
"""

from __future__ import annotations

import random

from rate_manual import (
    AGE_BANDS,
    BREED_FACTORS,
    DEDUCTIBLES,
    PLANS,
    TERRITORY_FACTORS,
)

FULL_COMBO_COUNT = (
    len(TERRITORY_FACTORS["v1"])
    * len(BREED_FACTORS["v1"])
    * len(AGE_BANDS["v1"])
    * len(PLANS)
    * len(DEDUCTIBLES)
)


def quote_combinations() -> list[dict]:
    """Every (territory, breed, band, plan, deductible) combination, once."""
    combos = []
    counter = 0
    for territory in TERRITORY_FACTORS["v1"]:
        for breed_group in BREED_FACTORS["v1"]:
            for band in AGE_BANDS["v1"]:
                width = band["max_age"] - band["min_age"] + 1
                for plan in PLANS:
                    for deductible in DEDUCTIBLES:
                        age = band["min_age"] + (counter % width)
                        combos.append({
                            "territory": territory,
                            "state": territory.split("-")[0],
                            "breed_group": breed_group,
                            "pet_age_years": age,
                            "plan": plan,
                            "deductible": deductible,
                        })
                        counter += 1
    return combos


def generate_quotes(n: int = 50_000, seed: int = 20261012) -> list[dict]:
    """Generate ``n`` synthetic test quotes (default 50,000)."""
    rng = random.Random(seed)
    combos = quote_combinations()
    if n < len(combos):
        raise ValueError(f"n={n} is smaller than the full combo count {len(combos)}")
    quotes = [dict(c) for c in combos]
    for _ in range(n - len(combos)):
        base = rng.choice(combos)
        q = dict(base)
        q["pet_age_years"] = rng.randint(0, 15)
        quotes.append(q)
    rng.shuffle(quotes)
    for i, q in enumerate(quotes):
        q["quote_id"] = f"Q-{i + 1:06d}"
    return quotes


def generate_policies(n: int = 120_000, seed: int = 20261013) -> list[dict]:
    """Generate ``n`` synthetic in-force policies for dislocation analysis."""
    rng = random.Random(seed)
    combos = quote_combinations()
    policies = []
    for i in range(n):
        base = rng.choice(combos)
        p = dict(base)
        p["pet_age_years"] = rng.randint(0, 15)
        p["policy_id"] = f"POL-{i + 1:07d}"
        policies.append(p)
    return policies

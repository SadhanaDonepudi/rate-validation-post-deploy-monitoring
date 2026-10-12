"""Deployed rating engine - the system under test.

The engine reads its rating parameters from the deployed CSV rate tables
(the files a release pipeline would ship), not from the approved manual.
The validation suite compares this engine against the independent reference
implementation in :mod:`rate_manual`.

Documented engine behaviors (part of the engine contract):
  * duplicate keys in a table: the LAST row wins;
  * missing territory key: the territory factor defaults to 1.00 and the
    quote is flagged (``territory_defaulted``);
  * pet age not covered by any age band: the quote is UNRATED
    (``premium_cents`` is None) - the engine refuses to price it;
  * missing breed / plan / deductible key: raises ``KeyError`` (hard fail).

ALL DATA IN THIS REPOSITORY IS SYNTHETIC.
"""

from __future__ import annotations

import csv
import os

MISSING_TERRITORY_DEFAULT = 1.00


def _read_table(table_dir: str, filename: str, version: str) -> list[dict]:
    path = os.path.join(table_dir, filename)
    with open(path, newline="", encoding="utf-8") as fh:
        return [row for row in csv.DictReader(fh) if row["version"] == version]


class RatingEngine:
    """Rating engine bound to one deployed table directory and version."""

    def __init__(self, table_dir: str, version: str):
        self.table_dir = table_dir
        self.version = version

        base_rows = _read_table(table_dir, "base_rates.csv", version)
        self.base = float(base_rows[0]["annual_base_premium"])

        # Last row wins on duplicate keys (documented contract).
        self.territories = {}
        for row in _read_table(table_dir, "territories.csv", version):
            self.territories[row["territory_code"]] = float(row["factor"])

        self.breeds = {}
        for row in _read_table(table_dir, "breeds.csv", version):
            self.breeds[row["breed_group"]] = float(row["factor"])

        self.age_bands = []
        for row in _read_table(table_dir, "age_bands.csv", version):
            self.age_bands.append({
                "band_id": row["band_id"],
                "band_label": row["band_label"],
                "min_age": int(row["min_age"]),
                "max_age": int(row["max_age"]),
                "factor": float(row["factor"]),
            })

        self.plans = {}
        for row in _read_table(table_dir, "plans.csv", version):
            self.plans[row["plan"]] = float(row["factor"])

        self.deductibles = {}
        for row in _read_table(table_dir, "deductibles.csv", version):
            self.deductibles[int(row["deductible"])] = float(row["factor"])

    def _resolve_age_band(self, age_years: int):
        for band in self.age_bands:
            if band["min_age"] <= age_years <= band["max_age"]:
                return band
        return None

    def calculate_premium(self, quote: dict) -> dict:
        """Rate a quote. Returns dict with premium_cents (or None if unrated)."""
        notes = []
        factors = {"base": self.base}

        territory = quote["territory"]
        if territory in self.territories:
            factors["territory"] = self.territories[territory]
        else:
            factors["territory"] = MISSING_TERRITORY_DEFAULT
            notes.append("territory_defaulted")

        factors["breed"] = self.breeds[quote["breed_group"]]          # KeyError if absent
        factors["plan"] = self.plans[quote["plan"]]                    # KeyError if absent
        factors["deductible"] = self.deductibles[quote["deductible"]]  # KeyError if absent

        band = self._resolve_age_band(quote["pet_age_years"])
        if band is None:
            return {
                "premium_cents": None,
                "unrated": True,
                "unrated_reason": "no_age_band",
                "factors": factors,
                "band_label": None,
                "notes": notes,
            }
        factors["age"] = band["factor"]

        # Manual section 4.2 - same published formula the reference implements.
        premium = round(
            factors["base"] * factors["territory"] * factors["breed"]
            * factors["age"] * factors["plan"] * factors["deductible"] + 1e-9, 2,
        )
        return {
            "premium_cents": int(round(premium * 100)),
            "unrated": False,
            "factors": factors,
            "band_label": band["band_label"],
            "notes": notes,
        }

"""Bundled Kenneth French–style monthly factor table (decimals). I/O lives here, not in ``quant``."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

_FACTOR_PATH = Path(__file__).resolve().parents[2] / "data" / "factors" / "fama_french_m.csv"


@dataclass(frozen=True)
class FamaFrenchMonth:
    ym: int
    mkt_rf: float
    smb: float
    hml: float
    rf: float


def load_fama_french_monthly(path: Path | None = None) -> list[FamaFrenchMonth]:
    p = path or _FACTOR_PATH
    with p.open("r", encoding="utf-8", newline="") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#") and ln.strip()]
    rdr = csv.DictReader(lines)
    rows: list[FamaFrenchMonth] = []
    for row in rdr:
        if not row.get("ym"):
            continue
        ym = int(str(row["ym"]).strip().replace("-", ""))
        rows.append(
            FamaFrenchMonth(
                ym=ym,
                mkt_rf=float(str(row["Mkt-RF"]).strip()),
                smb=float(str(row["SMB"]).strip()),
                hml=float(str(row["HML"]).strip()),
                rf=float(str(row["RF"]).strip()),
            )
        )
    if not rows:
        raise ValueError("empty Fama–French table")
    return rows


def by_year_month_index(rows: list[FamaFrenchMonth]) -> dict[int, FamaFrenchMonth]:
    return {r.ym: r for r in rows}


__all__ = [
    "FamaFrenchMonth",
    "by_year_month_index",
    "load_fama_french_monthly",
    "_FACTOR_PATH",
]

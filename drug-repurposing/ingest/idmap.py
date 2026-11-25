import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger("ingest.idmap")


@dataclass
class MappingReport:
    name: str
    total: int
    mapped: int
    unmapped_ids: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 1.0 if self.total == 0 else self.mapped / self.total

    def write_unmapped(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.name}.txt"
        path.write_text("".join(f"{x}\n" for x in self.unmapped_ids))
        return path

    def as_dict(self, unmapped_file: Path) -> dict[str, Any]:
        return {
            "total_unique": self.total,
            "mapped_unique": self.mapped,
            "unmapped_unique": len(self.unmapped_ids),
            "coverage": round(self.coverage, 6),
            "unmapped_file": str(unmapped_file),
        }


def map_values(
    name: str, values: pd.Series, mapping: dict[str, int]
) -> tuple[pd.Series, MappingReport]:
    mapped = values.map(mapping).astype("Int64")
    unique = pd.unique(values.dropna())
    missing = sorted(str(v) for v in unique if v not in mapping)
    report = MappingReport(name, len(unique), len(unique) - len(missing), missing)
    if missing:
        log.warning(
            "%s: %d of %d unique ids unmapped (coverage %.4f)",
            name,
            len(missing),
            len(unique),
            report.coverage,
        )
    return mapped, report

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(*parts: str | Path) -> Path:
    return PROJECT_ROOT.joinpath(*map(Path, parts))


def ensure_dir(path: str | Path) -> Path:
    output = Path(path)
    output.mkdir(parents=True, exist_ok=True)
    return output


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_column_name(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.strip().lower()
    text = text.replace("%", " percent ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    aliases = {"pm2_5": "pm25", "pm_2_5": "pm25", "pm_10": "pm10"}
    return aliases.get(text, text)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    copy = df.copy()
    copy.columns = [normalize_column_name(column) for column in copy.columns]
    return copy


def first_existing_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    normalized_columns = {normalize_column_name(column): column for column in columns}
    for candidate in candidates:
        normalized = normalize_column_name(candidate)
        if normalized in normalized_columns:
            return normalized_columns[normalized]
    return None


def detect_separator(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        counts = {sep: sample.count(sep) for sep in [",", ";", "\t"]}
        return max(counts, key=counts.get)


def read_csv_flexible(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    raw = csv_path.read_bytes()
    sample_text = ""
    last_error: Exception | None = None
    for encoding in ["utf-8", "utf-8-sig", "latin1"]:
        try:
            sample_text = raw[:8192].decode(encoding)
            sep = detect_separator(sample_text)
            return pd.read_csv(csv_path, sep=sep, encoding=encoding)
        except Exception as exc:  # pragma: no cover - exact pandas parser errors vary
            last_error = exc
    raise ValueError(f"Unable to read CSV {csv_path}: {last_error}") from last_error


def write_json(path: str | Path, payload: object) -> None:
    output_path = Path(path)
    ensure_dir(output_path.parent)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: str | Path, default: object | None = None) -> object:
    json_path = Path(path)
    if not json_path.exists():
        return default
    return json.loads(json_path.read_text(encoding="utf-8"))


def write_schema_report(processed_dir: str | Path, warnings: list[dict]) -> None:
    report_path = Path(processed_dir) / "schema_report.json"
    existing = read_json(report_path, default={"warnings": []})
    if not isinstance(existing, dict):
        existing = {"warnings": []}
    existing.setdefault("warnings", [])
    existing["warnings"].extend(warnings)
    existing["updated_at"] = utc_now_iso()
    write_json(report_path, existing)


def safe_to_parquet(df: pd.DataFrame, path: str | Path) -> None:
    output = Path(path)
    ensure_dir(output.parent)
    try:
        df.to_parquet(output, index=False)
    except Exception as exc:
        csv_path = output.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        print(
            f"Could not write parquet {output}. Wrote CSV fallback {csv_path}. "
            f"Install pyarrow to enable parquet output. Original error: {exc}"
        )


def safe_read_table(path: str | Path) -> pd.DataFrame:
    table_path = Path(path)
    if table_path.exists():
        return pd.read_parquet(table_path)
    csv_path = table_path.with_suffix(".csv")
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return pd.DataFrame()

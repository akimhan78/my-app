"""Build a compact, browser-ready dataset for the Cloudflare Pages dashboard.

Run this script after placing the yearly source files in deployment_data/.
It keeps the monthly district and legal-dong aggregates needed by the charts,
so a visitor does not have to download the much larger transaction-level files.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "deployment_data"
PUBLIC_DATA_DIR = ROOT / "public" / "data"
GEOJSON_PATH = SOURCE_DIR / "seoul_sigungu_4326.geojson"

USE_COLUMNS = [
    "계약일",
    "전월세구분",
    "보증금(만원)",
    "자치구명",
    "법정동명",
    "임대면적",
]


def read_source(path: Path) -> pd.DataFrame:
    """Read one CSV/TXT export, trying the encodings used by the source files."""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(
                path,
                compression="gzip",
                encoding=encoding,
                usecols=USE_COLUMNS,
                low_memory=False,
            )
        except UnicodeDecodeError as error:
            last_error = error
    raise UnicodeError(f"Cannot decode source file: {path}") from last_error


def to_month_rows(grouped: pd.DataFrame, keys: list[str], months: list[str]) -> dict:
    """Convert a grouped table into compact, ordered monthly observations."""
    result: dict = {}
    for identity, rows in grouped.groupby(keys, sort=True, dropna=False):
        if not isinstance(identity, tuple):
            identity = (identity,)
        key = "|".join(str(value) for value in identity)
        by_month = rows.set_index("연월")
        result[key] = [
            {
                "month": month,
                "price": (
                    round(float(by_month.at[month, "sqm_median"]), 4)
                    if month in by_month.index and pd.notna(by_month.at[month, "sqm_median"])
                    else None
                ),
                "deposit": (
                    round(float(by_month.at[month, "deposit_median"]), 2)
                    if month in by_month.index and pd.notna(by_month.at[month, "deposit_median"])
                    else None
                ),
                "count": (
                    int(by_month.at[month, "count"])
                    if month in by_month.index
                    else 0
                ),
            }
            for month in months
        ]
    return result


def main() -> None:
    source_files = sorted(SOURCE_DIR.glob("*.gz"))
    if not source_files:
        raise FileNotFoundError(f"No .gz source files found under {SOURCE_DIR}")

    cleaned_parts: list[pd.DataFrame] = []
    for source_path in source_files:
        raw = read_source(source_path)

        # Keep only jeonse records and normalize dates and numeric columns before
        # deriving the price-per-square-meter measure.
        rows = raw.loc[raw["전월세구분"].astype("string").str.strip().eq("전세")].copy()
        date_text = (
            rows["계약일"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
        )
        rows["계약일"] = pd.to_datetime(date_text, format="%Y%m%d", errors="coerce")
        rows["보증금(만원)"] = pd.to_numeric(
            rows["보증금(만원)"].astype("string").str.replace(",", "", regex=False),
            errors="coerce",
        )
        rows["임대면적"] = pd.to_numeric(
            rows["임대면적"].astype("string").str.replace(",", "", regex=False),
            errors="coerce",
        )
        for column in ("자치구명", "법정동명"):
            rows[column] = rows[column].astype("string").str.strip()
        rows = rows.dropna(subset=USE_COLUMNS)
        rows = rows.loc[(rows["임대면적"] > 0) & (rows["보증금(만원)"] > 0)].copy()
        rows["㎡당전세가격"] = rows["보증금(만원)"] / rows["임대면적"]
        rows["연월"] = rows["계약일"].dt.strftime("%Y-%m")
        cleaned_parts.append(
            rows[["계약일", "연월", "자치구명", "법정동명", "보증금(만원)", "㎡당전세가격"]]
        )
        print(f"Loaded {source_path.name}: {len(rows):,} valid jeonse rows")

    data = pd.concat(cleaned_parts, ignore_index=True)
    latest_date = data["계약일"].max()
    start_date = latest_date - pd.DateOffset(years=5)
    data = data.loc[data["계약일"] >= start_date].copy()
    months = sorted(data["연월"].unique().tolist())

    # Monthly medians and counts power all trend charts and summary metrics.
    district_monthly = (
        data.groupby(["자치구명", "연월"], as_index=False)
        .agg(
            sqm_median=("㎡당전세가격", "median"),
            deposit_median=("보증금(만원)", "median"),
            count=("㎡당전세가격", "size"),
        )
    )
    seoul_monthly_grouped = (
        data.groupby("연월", as_index=False)
        .agg(
            sqm_median=("㎡당전세가격", "median"),
            deposit_median=("보증금(만원)", "median"),
            count=("㎡당전세가격", "size"),
        )
    )
    dong_monthly = (
        data.groupby(["자치구명", "법정동명", "연월"], as_index=False)
        .agg(
            sqm_median=("㎡당전세가격", "median"),
            deposit_median=("보증금(만원)", "median"),
            count=("㎡당전세가격", "size"),
        )
    )

    latest_month = pd.Period(max(months), freq="M")
    year_start = latest_month - 11
    period_index = pd.PeriodIndex(data["연월"], freq="M")
    recent_year_medians = (
        data.loc[period_index >= year_start]
        .groupby("자치구명")["㎡당전세가격"]
        .median()
        .to_dict()
    )

    district_map = to_month_rows(district_monthly, ["자치구명"], months)
    dong_map = to_month_rows(dong_monthly, ["자치구명", "법정동명"], months)
    seoul_by_month = seoul_monthly_grouped.set_index("연월")
    seoul_monthly = [
        {
            "month": month,
            "price": round(float(seoul_by_month.at[month, "sqm_median"]), 4)
            if month in seoul_by_month.index and pd.notna(seoul_by_month.at[month, "sqm_median"])
            else None,
            "deposit": round(float(seoul_by_month.at[month, "deposit_median"]), 2)
            if month in seoul_by_month.index and pd.notna(seoul_by_month.at[month, "deposit_median"])
            else None,
            "count": int(seoul_by_month.at[month, "count"])
            if month in seoul_by_month.index
            else 0,
        }
        for month in months
    ]
    districts = [
        {
            "name": name,
            "recentYearMedian": round(float(recent_year_medians[name]), 4)
            if name in recent_year_medians and pd.notna(recent_year_medians[name])
            else None,
            "monthly": district_map[name],
        }
        for name in sorted(district_map)
    ]
    dongs = [
        {
            "district": key.split("|", 1)[0],
            "name": key.split("|", 1)[1],
            "monthly": monthly,
        }
        for key, monthly in sorted(dong_map.items())
    ]

    with GEOJSON_PATH.open("r", encoding="utf-8") as source:
        geojson = json.load(source)

    payload = {
        "latestDate": latest_date.strftime("%Y-%m-%d"),
        "startDate": start_date.strftime("%Y-%m-%d"),
        "months": months,
        "seoulMonthly": seoul_monthly,
        "districts": districts,
        "dongs": dongs,
        "geojson": geojson,
    }

    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PUBLIC_DATA_DIR / "dashboard.json.gz"
    with output_path.open("wb") as output_file:
        with gzip.GzipFile(fileobj=output_file, mode="wb", compresslevel=9, mtime=0) as compressed:
            compressed.write(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
                    "utf-8"
                )
            )

    print(f"Analysis dates: {data['계약일'].min():%Y-%m-%d} to {latest_date:%Y-%m-%d}")
    print(f"Rows included: {len(data):,}")
    print(f"Districts: {len(districts)}; legal dongs: {len(dongs)}; months: {len(months)}")
    print(f"Wrote {output_path} ({output_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

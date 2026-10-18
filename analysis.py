from pathlib import Path

import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# 이 스크립트가 있는 폴더 아래에서 연도별 원본 파일을 찾습니다.
DATA_DIR = Path(__file__).resolve().parent

# 결측치가 있으면 분석할 수 없는 핵심 컬럼입니다.
CORE_COLUMNS = [
    "계약일",
    "보증금(만원)",
    "자치구명",
    "법정동명",
    "임대면적",
]


def read_data_file(file_path: Path) -> pd.DataFrame:
    """CSV 또는 TXT 파일을 읽습니다.

    공공데이터 파일에서 자주 쓰이는 인코딩을 차례로 시도합니다.
    파일들은 쉼표로 구분되어 있어 pandas 기본 CSV 구분자를 사용합니다.
    """
    last_error = None

    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            # 원본 파일은 쉼표로 구분되므로 기본 C 엔진을 사용해 빠르게 읽습니다.
            return pd.read_csv(file_path, encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error

    raise UnicodeError(f"파일 인코딩을 확인할 수 없습니다: {file_path}") from last_error


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """전세 분석에 필요한 데이터만 순서대로 전처리합니다."""
    # 원본 데이터프레임을 직접 바꾸지 않도록 복사본을 사용합니다.
    df = df.copy()
    rows_before = len(df)

    # 전월세구분에서 '전세'만 남깁니다.
    # 월세 등 분석 대상이 아닌 계약을 제외해 전세 가격 통계를 계산합니다.
    df = df.loc[df["전월세구분"].eq("전세")].copy()

    # 계약일을 날짜형으로 변환합니다.
    # 원본에는 20210317 같은 8자리 날짜가 있으므로 문자열로 바꾼 뒤
    # YYYYMMDD 형식으로 먼저 해석합니다. 다른 날짜 형식도 있을 수 있어
    # 첫 변환에 실패한 값은 pandas의 기본 날짜 해석을 한 번 더 적용합니다.
    contract_date_text = (
        df["계약일"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    contract_dates = pd.to_datetime(
        contract_date_text,
        format="%Y%m%d",
        errors="coerce",
    )
    other_date_format = contract_dates.isna()
    contract_dates.loc[other_date_format] = pd.to_datetime(
        contract_date_text.loc[other_date_format],
        errors="coerce",
    )
    df["계약일"] = contract_dates

    # 보증금을 숫자형으로 변환합니다.
    # 문자열의 쉼표를 먼저 제거하고, 숫자로 해석할 수 없는 값은 결측치로 둡니다.
    deposit_text = df["보증금(만원)"].astype("string").str.replace(",", "", regex=False)
    df["보증금(만원)"] = pd.to_numeric(deposit_text, errors="coerce")

    # 임대면적을 숫자형으로 변환합니다.
    # 숫자 연산과 ㎡당 가격 계산을 할 수 있도록 형식을 통일합니다.
    area_text = df["임대면적"].astype("string").str.replace(",", "", regex=False)
    df["임대면적"] = pd.to_numeric(area_text, errors="coerce")

    # 자치구명과 법정동명의 앞뒤 공백을 제거합니다.
    # 공백 차이 때문에 같은 지역이 서로 다른 값으로 집계되는 것을 방지합니다.
    for column in ("자치구명", "법정동명"):
        df[column] = df[column].astype("string").str.strip()
        # 공백만 있던 값은 빈 문자열이 되므로 결측치로 통일합니다.
        df[column] = df[column].replace("", pd.NA)

    # 핵심 컬럼에 결측치가 있는 행을 제거합니다.
    # 날짜, 가격, 면적, 지역 정보가 모두 있어야 분석에 사용할 수 있습니다.
    df = df.dropna(subset=CORE_COLUMNS).copy()

    # 임대면적이 0 이하인 행을 제거합니다.
    # 0 이하 면적은 유효한 주거 면적으로 보기 어렵고, ㎡당 가격 계산도 불가능합니다.
    df = df.loc[df["임대면적"] > 0].copy()

    # 보증금이 0 이하인 행을 제거합니다.
    # 전세 가격 수준을 비교하기 위한 유효한 보증금 데이터만 남깁니다.
    df = df.loc[df["보증금(만원)"] > 0].copy()

    rows_after = len(df)
    removed_rows = rows_before - rows_after

    print("\n[전처리 행 개수]")
    print(f"전처리 전: {rows_before:,}행")
    print(f"전처리 후: {rows_after:,}행")
    print(f"제거된 행: {removed_rows:,}행")

    return df


def add_analysis_variables_and_filter_recent_years(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """분석 변수를 만들고 데이터 최대 계약일 기준 최근 5년만 반환합니다."""
    # 전처리 결과를 보존하고 분석용 복사본에 새 컬럼을 추가합니다.
    df = df.copy()

    if df.empty:
        raise ValueError("전처리 후 남은 데이터가 없어 분석 변수를 만들 수 없습니다.")

    # 계약일에서 연도를 가져와 연도별 분석에 사용할 수 있게 합니다.
    df["연도"] = df["계약일"].dt.year

    # YYYY-MM 형식은 연도와 월이 큰 단위부터 고정 자릿수로 표시됩니다.
    # 따라서 문자열로 정렬해도 시간 순서와 동일하게 정렬됩니다.
    df["연월"] = df["계약일"].dt.strftime("%Y-%m")

    # 보증금은 만원 단위이므로 이 값도 만원/㎡ 단위입니다.
    df["㎡당전세가격"] = df["보증금(만원)"] / df["임대면적"]

    # 시스템의 현재 날짜 대신, 데이터에 실제로 존재하는 가장 최근 계약일을 기준으로 합니다.
    latest_contract_date = df["계약일"].max()
    cutoff_date = latest_contract_date - pd.DateOffset(years=5)

    # 기준일에서 5년을 뺀 날짜부터 가장 최근 계약일까지의 데이터를 남깁니다.
    recent_df = df.loc[df["계약일"] >= cutoff_date].copy()

    # 요청한 최근 5년 범위의 시작일, 종료일, 행 개수를 출력합니다.
    print("\n[최근 5년 데이터 범위]")
    print(f"기준일(데이터 최대 계약일): {latest_contract_date:%Y-%m-%d}")
    print(f"필터 시작일: {cutoff_date:%Y-%m-%d}")
    print(f"최소 계약일: {recent_df['계약일'].min():%Y-%m-%d}")
    print(f"최대 계약일: {recent_df['계약일'].max():%Y-%m-%d}")
    print(f"데이터 건수: {len(recent_df):,}건")

    return recent_df


def inspect_distributions(df: pd.DataFrame) -> None:
    """주요 숫자 변수의 요약 통계와 분포 그래프를 확인합니다.

    이 함수는 이상치 후보를 눈으로 확인하기 위한 것으로,
    어떤 행이나 값을 자동으로 제거하지 않습니다.
    """
    columns = ["보증금(만원)", "임대면적", "㎡당전세가격"]
    quantile_levels = [0.01, 0.25, 0.50, 0.75, 0.99]

    # 각 변수의 기본 통계량과 요청한 분위수를 출력합니다.
    for column in columns:
        print(f"\n[{column} 분포 요약]")
        print("describe():")
        print(df[column].describe())

        print("\n1%, 25%, 50%, 75%, 99% 분위수:")
        print(df[column].quantile(quantile_levels))

    # 각 변수별 Box Plot과 Histogram을 만듭니다.
    # Box Plot의 점은 이상치 후보를 보여주며, 데이터에서 제거하지 않습니다.
    for column in columns:
        box_fig = px.box(
            df,
            y=column,
            points="outliers",
            title=f"{column} Box Plot (이상치 후보 확인)",
            labels={column: column},
        )
        box_fig.show()

        histogram_fig = px.histogram(
            df,
            x=column,
            title=f"{column} Histogram",
            labels={column: column},
            nbins=50,
        )
        histogram_fig.show()


def analyze_monthly_seoul_trend(df: pd.DataFrame) -> pd.DataFrame:
    """서울 전체의 월별 전세가격 요약과 ㎡당 가격 추이를 계산합니다."""
    # 연월은 YYYY-MM 문자열이므로 문자열 오름차순이 시간 오름차순과 같습니다.
    monthly_summary = (
        df.groupby("연월", as_index=False, sort=True)
        .agg(
            **{
                "㎡당 전세가격 중앙값": ("㎡당전세가격", "median"),
                "실제 보증금 중앙값": ("보증금(만원)", "median"),
                "거래 건수": ("보증금(만원)", "size"),
            }
        )
        .sort_values("연월")
        .reset_index(drop=True)
    )

    # 실제 집계값을 출력해 표의 수치와 그래프의 기준 데이터를 확인할 수 있게 합니다.
    print("\n[서울 전체 월별 전세가격 집계]")
    print(monthly_summary.to_string(index=False))

    # 최고·최저 값과 해당 월은 월별 집계 데이터에서 직접 계산합니다.
    highest_value = monthly_summary["㎡당 전세가격 중앙값"].max()
    lowest_value = monthly_summary["㎡당 전세가격 중앙값"].min()
    highest_months = monthly_summary.loc[
        monthly_summary["㎡당 전세가격 중앙값"] == highest_value
    ]
    lowest_months = monthly_summary.loc[
        monthly_summary["㎡당 전세가격 중앙값"] == lowest_value
    ]

    print("\n[월별 ㎡당 전세가격 중앙값 최고 시점]")
    print(
        highest_months[
            ["연월", "㎡당 전세가격 중앙값", "실제 보증금 중앙값", "거래 건수"]
        ].to_string(index=False)
    )
    print("\n[월별 ㎡당 전세가격 중앙값 최저 시점]")
    print(
        lowest_months[
            ["연월", "㎡당 전세가격 중앙값", "실제 보증금 중앙값", "거래 건수"]
        ].to_string(index=False)
    )

    # Plotly 선 그래프의 hover에는 연월, 해당 월의 중앙값, 거래 건수를 표시합니다.
    line_fig = px.line(
        monthly_summary,
        x="연월",
        y="㎡당 전세가격 중앙값",
        custom_data=["거래 건수"],
        markers=True,
        category_orders={"연월": monthly_summary["연월"].tolist()},
        title="서울 전체 월별 ㎡당 전세가격 중앙값 추이",
        labels={
            "연월": "연월",
            "㎡당 전세가격 중앙값": "㎡당 전세가격 중앙값 (만원/㎡)",
        },
    )
    line_fig.update_traces(
        hovertemplate=(
            "연월: %{x}<br>"
            "㎡당 전세가격 중앙값: %{y:,.2f} 만원/㎡<br>"
            "거래 건수: %{customdata[0]:,}건"
            "<extra></extra>"
        )
    )
    line_fig.update_layout(
        xaxis_title="연월",
        yaxis_title="㎡당 전세가격 중앙값 (만원/㎡)",
    )
    line_fig.show()

    return monthly_summary


def aggregate_district_monthly(df: pd.DataFrame, district: str) -> pd.DataFrame:
    """한 자치구의 월별 중앙값과 실제 보증금 중앙값, 거래 건수를 집계합니다.

    Streamlit 등 다른 화면에서도 재사용할 수 있도록 그래프를 만들지 않고
    정렬된 월별 DataFrame만 반환합니다.
    """
    district_data = df.loc[df["자치구명"] == district]
    if district_data.empty:
        raise ValueError(f"분석 데이터에서 자치구를 찾을 수 없습니다: {district}")

    # 분석 기간의 모든 달을 포함해 거래가 없던 월도 누락되지 않게 합니다.
    all_months = pd.period_range(
        start=pd.Period(df["연월"].min(), freq="M"),
        end=pd.Period(df["연월"].max(), freq="M"),
        freq="M",
    ).astype(str).tolist()

    monthly = (
        district_data.groupby("연월")
        .agg(
            **{
                "㎡당 전세가격 중앙값": ("㎡당전세가격", "median"),
                "실제 보증금 중앙값": ("보증금(만원)", "median"),
                "거래 건수": ("㎡당전세가격", "size"),
            }
        )
        .reindex(all_months)
        .rename_axis("연월")
        .reset_index()
    )
    monthly["거래 건수"] = monthly["거래 건수"].fillna(0).astype(int)
    monthly["자치구명"] = district
    return monthly


def summarize_district_monthly(monthly: pd.DataFrame) -> dict:
    """월 집계표에서 비교용 요약 통계를 계산합니다."""
    observed = monthly.loc[monthly["거래 건수"] > 0].copy()
    if observed.empty:
        raise ValueError("요약 통계를 계산할 월별 거래가 없습니다.")

    latest = observed.iloc[-1]
    latest_period = pd.Period(latest["연월"], freq="M")
    latest_price = latest["㎡당 전세가격 중앙값"]

    # 최근 1년은 최신 월과 정확히 12개월 전 같은 달을 비교합니다.
    one_year_ago = latest_period - 12
    one_year_base = observed.loc[
        observed["연월"] == str(one_year_ago), "㎡당 전세가격 중앙값"
    ]
    one_year_change = (
        (latest_price / one_year_base.iloc[0] - 1) * 100
        if not one_year_base.empty and one_year_base.iloc[0] != 0
        else float("nan")
    )

    # 최근 5년은 분석 기간 중 가장 이른 거래 월과 최신 거래 월을 비교합니다.
    earliest = observed.iloc[0]
    five_year_change = (
        (latest_price / earliest["㎡당 전세가격 중앙값"] - 1) * 100
        if earliest["㎡당 전세가격 중앙값"] != 0
        else float("nan")
    )

    # 월별 변동성은 인접 월별 가격 중앙값의 전월 대비 변화율 표준편차입니다.
    monthly_returns = monthly["㎡당 전세가격 중앙값"].pct_change(fill_method=None).dropna()

    return {
        "최근 가격 수준(만원/㎡)": latest_price,
        "최근 1년 가격 변화율(%)": one_year_change,
        "최근 5년 가격 변화율(%)": five_year_change,
        "월별 가격 변동성(%)": monthly_returns.std() * 100,
        "거래 건수": int(monthly["거래 건수"].sum()),
    }


def recommend_similar_districts(
    df: pd.DataFrame,
    selected_district: str,
    top_n: int = 3,
) -> dict:
    """통계 feature와 z-score 기반 유클리드 거리로 유사 자치구를 추천합니다.

    반환값의 recommendation 표에는 순위, 거리, 원래 단위의 통계값이 담기고,
    line_fig에는 기준 자치구와 추천 자치구들의 월별 가격 추이가 담깁니다.
    """
    district_names = sorted(df["자치구명"].dropna().unique().tolist())
    if selected_district not in district_names:
        raise ValueError(f"분석 데이터에 자치구가 없습니다: {selected_district}")
    if top_n < 1:
        raise ValueError("top_n은 1 이상의 정수여야 합니다.")

    # 최근 1년은 데이터의 최신 연월을 포함한 12개 달로 정합니다.
    latest_month = pd.Period(df["연월"].max(), freq="M")
    first_month_of_recent_year = latest_month - 11
    month_periods = pd.PeriodIndex(df["연월"], freq="M")
    recent_year_data = df.loc[month_periods >= first_month_of_recent_year]

    # 각 자치구에 대해 유사도에 사용할 세 가지 지역 통계 feature를 계산합니다.
    feature_rows = []
    for district in district_names:
        district_recent_year = recent_year_data.loc[
            recent_year_data["자치구명"] == district
        ]

        # 최근 1년 가격 feature는 해당 기간 거래의 ㎡당 가격 중앙값입니다.
        recent_year_price = district_recent_year["㎡당전세가격"].median()

        # 앞서 정의한 월 집계 통계에서 5년 변화율과 월별 변동성을 가져옵니다.
        monthly = aggregate_district_monthly(df, district)
        monthly_stats = summarize_district_monthly(monthly)

        feature_rows.append(
            {
                "자치구명": district,
                "최근 1년 ㎡당 전세가격 중앙값": recent_year_price,
                "최근 5년 가격 변화율": monthly_stats["최근 5년 가격 변화율(%)"],
                "월별 가격 변동성": monthly_stats["월별 가격 변동성(%)"],
            }
        )

    features = pd.DataFrame(feature_rows).set_index("자치구명")
    feature_columns = [
        "최근 1년 ㎡당 전세가격 중앙값",
        "최근 5년 가격 변화율",
        "월별 가격 변동성",
    ]

    # 세 feature는 단위가 서로 다르므로 각각 표준화한 값만 거리 계산에 사용합니다.
    distance_features = features[feature_columns].copy()

    # 지표마다 평균 0, 표준편차 1이 되도록 z-score 표준화합니다.
    # 표준편차가 0인 지표는 모든 지역이 같은 값이므로 표준화 결과를 0으로 둡니다.
    feature_means = distance_features.mean()
    feature_stds = distance_features.std(ddof=0).replace(0, 1)
    standardized = (distance_features - feature_means) / feature_stds

    # 결측 feature가 있는 지역은 거리 계산이 불가능하므로 추천 후보에서 제외합니다.
    valid_rows = standardized.dropna(subset=feature_columns)
    if selected_district not in valid_rows.index:
        raise ValueError("선택한 자치구의 유사도 feature에 결측치가 있습니다.")
    if len(valid_rows) - 1 < top_n:
        raise ValueError("유사 지역 추천에 필요한 비교 자치구 수가 부족합니다.")

    # 표준화된 세 feature 차이의 제곱합에 제곱근을 취해 유클리드 거리를 구합니다.
    # 세 지표는 동일한 비중으로 계산합니다.
    target_vector = valid_rows.loc[selected_district]
    distances = np.sqrt(valid_rows.sub(target_vector, axis="columns").pow(2).sum(axis=1))
    distances = distances.drop(index=selected_district).sort_values()
    recommended_names = distances.head(top_n).index.tolist()

    # 결과표에는 계산에 사용한 변환값이 아닌 원래 단위의 feature 값을 보여줍니다.
    recommendations = features.loc[recommended_names].copy()
    recommendations.insert(0, "거리값", distances.loc[recommended_names].values)
    recommendations.insert(0, "자치구명", recommendations.index)
    recommendations.insert(0, "추천 순위", range(1, len(recommendations) + 1))
    recommendations = recommendations.reset_index(drop=True)
    recommendations = recommendations.rename(
        columns={
            "최근 1년 ㎡당 전세가격 중앙값": "최근 1년 ㎡당 전세가격 중앙값(만원/㎡)",
            "최근 5년 가격 변화율": "최근 5년 가격 변화율(%)",
            "월별 가격 변동성": "월별 가격 변동성(%)",
        }
    )

    # 기준 지역과 상위 추천 지역의 월별 가격 데이터를 한 표로 합칩니다.
    comparison_districts = [selected_district] + recommended_names
    trend_parts = []
    for district in comparison_districts:
        district_monthly = aggregate_district_monthly(df, district)
        district_monthly["지역"] = district
        trend_parts.append(district_monthly)
    trend_data = pd.concat(trend_parts, ignore_index=True)[
        ["연월", "지역", "㎡당 전세가격 중앙값"]
    ]
    month_order = trend_parts[0]["연월"].tolist()

    # 비교 그래프의 선은 집계된 월별 ㎡당 전세가격 중앙값을 사용합니다.
    line_fig = px.line(
        trend_data,
        x="연월",
        y="㎡당 전세가격 중앙값",
        color="지역",
        markers=True,
        category_orders={"연월": month_order, "지역": comparison_districts},
        title=f"{selected_district}와 유사 자치구 {len(recommended_names)}곳의 전세가격 추이",
        labels={
            "연월": "연월",
            "㎡당 전세가격 중앙값": "㎡당 전세가격 중앙값 (만원/㎡)",
            "지역": "자치구",
        },
    )
    line_fig.update_traces(
        connectgaps=False,
        hovertemplate=(
            "연월: %{x}<br>"
            "㎡당 전세가격 중앙값: %{y:,.2f} 만원/㎡<br>"
            "<extra>%{fullData.name}</extra>"
        ),
    )
    line_fig.update_layout(
        xaxis_title="연월",
        yaxis_title="㎡당 전세가격 중앙값 (만원/㎡)",
        legend_title="자치구",
    )

    return {
        "features": features.reset_index(),
        "standardized_features": standardized,
        "recommendations": recommendations,
        "trend_data": trend_data,
        "line_fig": line_fig,
    }


def verify_similarity_features(
    recommendation_result: dict,
    selected_district: str,
) -> pd.DataFrame:
    """추천별 원래 feature 값과 표준화 거리 기여도를 출력합니다.

    각 feature의 거리 기여도는 (추천 지역 z-score - 기준 지역 z-score)²입니다.
    세 기여도를 더한 뒤 제곱근을 취하면 추천 결과의 Euclidean Distance가 됩니다.
    """
    features = recommendation_result["features"].set_index("자치구명")
    standardized = recommendation_result["standardized_features"]
    recommendations = recommendation_result["recommendations"]

    feature_columns = [
        "최근 1년 ㎡당 전세가격 중앙값",
        "최근 5년 가격 변화율",
        "월별 가격 변동성",
    ]
    display_names = {
        "최근 1년 ㎡당 전세가격 중앙값": "최근 1년 ㎡당 가격 중앙값(만원/㎡)",
        "최근 5년 가격 변화율": "최근 5년 가격 변화율(%)",
        "월별 가격 변동성": "월별 가격 변동성(%)",
    }

    comparison_rows = []
    for _, recommendation in recommendations.iterrows():
        recommended_district = recommendation["자치구명"]
        for feature in feature_columns:
            reference_value = features.loc[selected_district, feature]
            recommended_value = features.loc[recommended_district, feature]
            reference_z = standardized.loc[selected_district, feature]
            recommended_z = standardized.loc[recommended_district, feature]
            standardized_difference = recommended_z - reference_z

            comparison_rows.append(
                {
                    "추천 순위": int(recommendation["추천 순위"]),
                    "추천 자치구": recommended_district,
                    "feature": display_names[feature],
                    "기준 지역 값": reference_value,
                    "추천 지역 값": recommended_value,
                    "추천-기준 차이": recommended_value - reference_value,
                    "표준화 차이": standardized_difference,
                    "거리 기여도(표준화 차이²)": standardized_difference**2,
                }
            )

    comparison_table = pd.DataFrame(comparison_rows)
    print(f"\n[기준 지역: {selected_district} / 추천 지역별 feature 비교]")
    print(comparison_table.to_string(index=False, float_format=lambda value: f"{value:,.4f}"))

    # feature 기여도의 합과 거리값을 함께 보여 어떤 feature가 거리를 키웠는지 확인합니다.
    print("\n[추천별 거리 기여도 요약]")
    contribution_summary = (
        comparison_table.groupby(["추천 순위", "추천 자치구"], as_index=False)
        .agg(거리_제곱합=("거리 기여도(표준화 차이²)", "sum"))
    )
    contribution_summary["계산된 거리값"] = np.sqrt(
        contribution_summary["거리_제곱합"]
    )
    contribution_summary = contribution_summary.merge(
        recommendations[["자치구명", "거리값"]],
        left_on="추천 자치구",
        right_on="자치구명",
        how="left",
    ).drop(columns="자치구명")
    print(contribution_summary.to_string(index=False, float_format=lambda value: f"{value:,.4f}"))

    return comparison_table


def compare_districts(
    df: pd.DataFrame,
    region_a: str,
    region_b: str,
) -> dict:
    """두 자치구를 비교해 월별 표, 통계 표, Plotly 그래프를 반환합니다.

    반환된 DataFrame과 Figure는 Streamlit의 st.dataframe() 및
    st.plotly_chart()에 전달해 재사용할 수 있습니다.
    """
    if region_a == region_b:
        raise ValueError("서로 다른 두 자치구를 선택해 주세요.")

    # 집계 단계는 그래프와 분리되어 있어 다른 화면에서도 그대로 사용할 수 있습니다.
    monthly_a = aggregate_district_monthly(df, region_a)
    monthly_b = aggregate_district_monthly(df, region_b)
    monthly_a["지역"] = region_a
    monthly_b["지역"] = region_b
    monthly_comparison = pd.concat([monthly_a, monthly_b], ignore_index=True)

    # 각 지역의 주요 지표를 한 표에 모읍니다.
    summary_a = summarize_district_monthly(monthly_a)
    summary_b = summarize_district_monthly(monthly_b)
    summary = pd.DataFrame(
        [
            {"지역": region_a, **summary_a},
            {"지역": region_b, **summary_b},
        ]
    )

    # 최근 5년 월별 가격 중앙값을 두 개의 선으로 비교합니다.
    line_fig = px.line(
        monthly_comparison,
        x="연월",
        y="㎡당 전세가격 중앙값",
        color="지역",
        custom_data=["거래 건수"],
        markers=True,
        category_orders={
            "연월": monthly_a["연월"].tolist(),
            "지역": [region_a, region_b],
        },
        title="자치구별 월별 ㎡당 전세가격 중앙값 비교",
        labels={
            "연월": "연월",
            "㎡당 전세가격 중앙값": "㎡당 전세가격 중앙값 (만원/㎡)",
            "지역": "자치구",
        },
    )
    line_fig.update_traces(
        connectgaps=False,
        hovertemplate=(
            "연월: %{x}<br>"
            "㎡당 전세가격 중앙값: %{y:,.2f} 만원/㎡<br>"
            "거래 건수: %{customdata[0]:,}건"
            "<extra>%{fullData.name}</extra>"
        ),
    )
    line_fig.update_layout(
        xaxis_title="연월",
        yaxis_title="㎡당 전세가격 중앙값 (만원/㎡)",
        legend_title="자치구",
    )

    # 서로 단위가 다른 지표를 한 축에 섞지 않도록 지표별 패널로 비교합니다.
    metric_specs = [
        ("최근 가격 수준(만원/㎡)", "최근 가격 수준", "만원/㎡", ",.2f"),
        ("최근 1년 가격 변화율(%)", "최근 1년 변화율", "%", ".2f"),
        ("최근 5년 가격 변화율(%)", "최근 5년 변화율", "%", ".2f"),
        ("월별 가격 변동성(%)", "월별 가격 변동성", "%", ".2f"),
        ("거래 건수", "거래 건수", "건", ",d"),
    ]
    bar_fig = make_subplots(
        rows=2,
        cols=3,
        subplot_titles=[spec[1] for spec in metric_specs] + [""],
        horizontal_spacing=0.12,
        vertical_spacing=0.22,
    )
    for index, (metric, title, unit, number_format) in enumerate(metric_specs):
        row = index // 3 + 1
        col = index % 3 + 1
        values = summary[metric].tolist()
        if number_format == ",d":
            text_values = [f"{int(value):,}" for value in values]
        else:
            text_values = [
                "계산 불가" if pd.isna(value) else format(value, number_format)
                for value in values
            ]
        bar_fig.add_trace(
            go.Bar(
                x=summary["지역"],
                y=values,
                text=text_values,
                textposition="auto",
                name=title,
                showlegend=False,
                hovertemplate=(
                    "자치구: %{x}<br>"
                    f"{title}: %{{y:{number_format}}} {unit}"
                    "<extra></extra>"
                ),
            ),
            row=row,
            col=col,
        )
        bar_fig.update_yaxes(title_text=unit, row=row, col=col)

    bar_fig.update_layout(
        title="두 자치구 주요 통계 비교",
        height=650,
        showlegend=False,
    )

    return {
        "monthly": monthly_comparison,
        "summary": summary,
        "line_fig": line_fig,
        "bar_fig": bar_fig,
    }


def get_legal_dongs(df: pd.DataFrame, selected_district: str) -> list[str]:
    """선택 자치구에 실제로 존재하는 법정동명 목록만 반환합니다."""
    district_data = df.loc[df["자치구명"] == selected_district]
    return sorted(district_data["법정동명"].dropna().unique().tolist())


def analyze_dong_trend(
    df: pd.DataFrame,
    selected_district: str,
    selected_dong: str,
    minimum_monthly_transactions: int = 5,
    show_plot: bool = True,
    verbose: bool = True,
) -> dict:
    """선택 동, 자치구 전체, 서울 전체 월별 가격과 요약 통계를 계산합니다.

    show_plot=True이면 일반 Python 실행에서 그래프를 직접 표시하고,
    False이면 Figure를 반환해 Streamlit 등에서 표시할 수 있습니다.
    """
    # 동은 자치구 안에서만 찾도록 두 지역 조건을 함께 적용합니다.
    dong_data = df.loc[
        (df["자치구명"] == selected_district)
        & (df["법정동명"] == selected_dong)
    ].copy()
    if dong_data.empty:
        raise ValueError(
            f"{selected_district}에 해당하는 법정동을 찾을 수 없습니다: {selected_dong}"
        )

    # 월별 누락 구간도 그래프에 표시할 수 있도록 전체 기간의 월 목록을 만듭니다.
    all_months = pd.period_range(
        start=pd.Period(df["연월"].min(), freq="M"),
        end=pd.Period(df["연월"].max(), freq="M"),
        freq="M",
    ).astype(str).tolist()

    def monthly_aggregate(source: pd.DataFrame, label: str) -> pd.DataFrame:
        """월별 중앙값과 거래 건수를 집계하고 모든 월을 포함시킵니다."""
        monthly = (
            source.groupby("연월")
            .agg(
                **{
                    "㎡당 전세가격 중앙값": ("㎡당전세가격", "median"),
                    "거래 건수": ("㎡당전세가격", "size"),
                }
            )
            .reindex(all_months)
            .rename_axis("연월")
            .reset_index()
        )
        # 거래가 없는 월은 0건으로 표시하고 가격 중앙값은 결측으로 둡니다.
        monthly["거래 건수"] = monthly["거래 건수"].fillna(0).astype(int)
        monthly["지역"] = label
        return monthly

    seoul_monthly = monthly_aggregate(df, "서울 전체")
    district_monthly = monthly_aggregate(
        df.loc[df["자치구명"] == selected_district],
        "자치구 전체",
    )
    dong_monthly = monthly_aggregate(dong_data, "선택 동")

    # 거래가 5건 미만인 동의 월 중앙값은 그래프에서만 숨깁니다.
    # 해당 월의 원래 거래 건수와 집계 중앙값은 dong_monthly에 그대로 남습니다.
    sparse_months = dong_monthly.loc[
        dong_monthly["거래 건수"] < minimum_monthly_transactions,
        ["연월", "거래 건수"],
    ].copy()
    dong_monthly_for_plot = dong_monthly.copy()
    dong_monthly_for_plot["㎡당 전세가격 중앙값"] = dong_monthly_for_plot[
        "㎡당 전세가격 중앙값"
    ].where(dong_monthly_for_plot["거래 건수"] >= minimum_monthly_transactions)

    print(
        f"\n[{selected_district} {selected_dong}: 거래 "
        f"{minimum_monthly_transactions}건 미만으로 그래프에서 비운 월]"
    )
    if verbose:
        if sparse_months.empty:
            print("해당 월이 없습니다.")
        else:
            print(sparse_months.to_string(index=False))

    # 세 지역 수준의 월별 결과를 하나로 합쳐 Plotly에서 색상별 선으로 표시합니다.
    comparison_data = pd.concat(
        [seoul_monthly, district_monthly, dong_monthly_for_plot],
        ignore_index=True,
    )
    line_fig = px.line(
        comparison_data,
        x="연월",
        y="㎡당 전세가격 중앙값",
        color="지역",
        custom_data=["거래 건수"],
        markers=True,
        category_orders={
            "연월": all_months,
            "지역": ["선택 동", "자치구 전체", "서울 전체"],
        },
        title=f"{selected_district} {selected_dong} · 자치구 · 서울 전체 전세가격 추이",
        labels={
            "연월": "연월",
            "㎡당 전세가격 중앙값": "㎡당 전세가격 중앙값 (만원/㎡)",
            "지역": "지역 범위",
        },
    )
    line_fig.update_traces(
        connectgaps=False,
        hovertemplate=(
            "연월: %{x}<br>"
            "㎡당 전세가격 중앙값: %{y:,.2f} 만원/㎡<br>"
            "거래 건수: %{customdata[0]:,}건"
            "<extra>%{fullData.name}</extra>"
        ),
    )
    line_fig.update_layout(
        xaxis_title="연월",
        yaxis_title="㎡당 전세가격 중앙값 (만원/㎡)",
        legend_title="지역 범위",
    )
    if show_plot:
        line_fig.show()

    # 동 요약 통계에도 그래프와 같은 월별 거래 기준을 적용합니다.
    # 거래가 적은 월은 가격 값을 비우고, 월별 변동성 계산에서도 제외합니다.
    dong_monthly_for_stats = dong_monthly.copy()
    sparse_mask = dong_monthly_for_stats["거래 건수"] < minimum_monthly_transactions
    dong_monthly_for_stats.loc[sparse_mask, "거래 건수"] = 0
    dong_monthly_for_stats.loc[sparse_mask, "㎡당 전세가격 중앙값"] = np.nan
    stable_dong_months = dong_monthly_for_stats.loc[
        dong_monthly_for_stats["거래 건수"] > 0
    ].copy()
    if stable_dong_months.empty:
        raise ValueError(
            f"{selected_district} {selected_dong}에는 월 5건 이상 거래된 달이 없습니다."
        )

    stable_dong_months["월"] = pd.PeriodIndex(stable_dong_months["연월"], freq="M")
    latest_dong_month = stable_dong_months.iloc[-1]
    latest_dong_period = latest_dong_month["월"]
    latest_dong_price = latest_dong_month["㎡당 전세가격 중앙값"]

    # 월 5건 이상인 최신 달과 12개월 전 같은 달의 가격을 비교합니다.
    dong_year_ago_period = latest_dong_period - 12
    dong_year_ago = stable_dong_months.loc[
        stable_dong_months["월"] == dong_year_ago_period,
        "㎡당 전세가격 중앙값",
    ]
    dong_year_change = (
        (latest_dong_price / dong_year_ago.iloc[0] - 1) * 100
        if not dong_year_ago.empty and dong_year_ago.iloc[0] != 0
        else float("nan")
    )
    first_stable_dong_month = stable_dong_months.iloc[0]
    dong_five_year_change = (
        (
            latest_dong_price
            / first_stable_dong_month["㎡당 전세가격 중앙값"]
            - 1
        )
        * 100
    )

    # 결측 월을 앞 값으로 채우지 않고, 인접한 유효 월별 변화율만 사용합니다.
    dong_monthly_returns = (
        dong_monthly_for_stats["㎡당 전세가격 중앙값"]
        .pct_change(fill_method=None)
        .dropna()
    )
    dong_summary = {
        "최근 가격 수준(만원/㎡)": latest_dong_price,
        "최근 1년 가격 변화율(%)": dong_year_change,
        "최근 5년 가격 변화율(%)": dong_five_year_change,
        "월별 가격 변동성(%)": dong_monthly_returns.std() * 100,
        # 표시용 거래 건수는 5건 미만 월도 포함한 실제 계약 행 수입니다.
        "거래 건수": int(dong_monthly["거래 건수"].sum()),
    }

    # 선택 자치구의 기존 요약 통계도 계속 계산해 반환합니다.
    district_for_stats = district_monthly.loc[district_monthly["거래 건수"] > 0].copy()
    district_for_stats["월"] = pd.PeriodIndex(district_for_stats["연월"], freq="M")
    latest_row = district_for_stats.iloc[-1]
    latest_period = latest_row["월"]
    latest_price = latest_row["㎡당 전세가격 중앙값"]

    one_year_ago_period = latest_period - 12
    one_year_ago_rows = district_for_stats.loc[
        district_for_stats["월"] == one_year_ago_period
    ]
    if one_year_ago_rows.empty:
        one_year_change = float("nan")
        one_year_base_month = "해당 월 자료 없음"
    else:
        one_year_base_price = one_year_ago_rows.iloc[0]["㎡당 전세가격 중앙값"]
        one_year_change = (latest_price / one_year_base_price - 1) * 100
        one_year_base_month = str(one_year_ago_period)

    five_year_base_row = district_for_stats.iloc[0]
    five_year_base_price = five_year_base_row["㎡당 전세가격 중앙값"]
    five_year_change = (latest_price / five_year_base_price - 1) * 100
    monthly_returns = district_for_stats["㎡당 전세가격 중앙값"].pct_change().dropna()
    monthly_volatility = monthly_returns.std() * 100
    total_transactions = int(district_for_stats["거래 건수"].sum())

    if verbose:
        print(f"\n[{selected_district} 요약 통계]")
        print(f"최근 가격 중앙값 ({latest_row['연월']}): {latest_price:,.2f} 만원/㎡")
        if pd.isna(one_year_change):
            print(f"최근 1년 가격 변화율: 계산 불가 ({one_year_base_month})")
        else:
            print(
                f"최근 1년 가격 변화율 ({one_year_base_month} 대비): "
                f"{one_year_change:+.2f}%"
            )
        print(
            f"최근 5년 가격 변화율 ({five_year_base_row['연월']} 대비): "
            f"{five_year_change:+.2f}%"
        )
        print(f"월별 가격 변동성 (월 변화율 표준편차): {monthly_volatility:.2f}%")
        print(f"전체 거래 건수: {total_transactions:,}건")

    district_summary = {
        "자치구명": selected_district,
        "법정동명": selected_dong,
        "최근 가격 중앙값(만원/㎡)": latest_price,
        "최근 1년 가격 변화율(%)": one_year_change,
        "최근 5년 가격 변화율(%)": five_year_change,
        "월별 가격 변동성(%)": monthly_volatility,
        "전체 거래 건수": total_transactions,
    }
    return {
        **district_summary,
        "district_summary": district_summary,
        "dong_summary": dong_summary,
        "line_fig": line_fig,
        "dong_monthly": dong_monthly,
        "district_monthly": district_monthly,
        "seoul_monthly": seoul_monthly,
    }


def create_seoul_choropleth_map(df: pd.DataFrame):
    """서울 25개 자치구의 최근 1년 ㎡당 전세가격 중앙값 지도를 만듭니다."""
    # 배포 환경에서는 서울 25개 구만 담은 정적 GeoJSON을 우선 사용합니다.
    geojson_path = DATA_DIR / "deployment_data" / "seoul_sigungu_4326.geojson"
    shapefile_path = (
        DATA_DIR.parents[2]
        / "1012"
        / "bnd_all_00_2025_2Q"
        / "bnd_sigungu_00_2025_2Q.shp"
    )
    seoul_boundaries = None
    geojson = None
    if geojson_path.exists():
        # 배포 GeoJSON은 EPSG:4326이며, 서울 구별 이름 필드가 포함되어 있습니다.
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
        boundary_names = {
            feature["properties"]["SIGUNGU_NM"]
            for feature in geojson.get("features", [])
        }
    else:
        # 배포 GeoJSON이 없으면 기존에 확인한 Shapefile을 이용합니다.
        if not shapefile_path.exists():
            raise FileNotFoundError(
                f"경계 GeoJSON 또는 시군구 Shapefile을 찾을 수 없습니다: {geojson_path}"
            )
        import geopandas as gpd

        seoul_district_names = {
            "종로구", "중구", "용산구", "성동구", "광진구",
            "동대문구", "중랑구", "성북구", "강북구", "도봉구",
            "노원구", "은평구", "서대문구", "마포구", "양천구",
            "강서구", "구로구", "금천구", "영등포구", "동작구",
            "관악구", "서초구", "강남구", "송파구", "강동구",
        }
        boundaries = gpd.read_file(shapefile_path)
        if "SIGUNGU_NM" not in boundaries.columns:
            raise KeyError("Shapefile에서 'SIGUNGU_NM' 필드를 찾을 수 없습니다.")
        if "SIGUNGU_CD" not in boundaries.columns:
            raise KeyError(
                "Shapefile에서 서울 경계 범위 확인에 필요한 'SIGUNGU_CD'를 찾을 수 없습니다."
            )
        seoul_codes = boundaries["SIGUNGU_CD"].astype(str).str.zfill(5)
        seoul_boundaries = boundaries.loc[
            seoul_codes.str.startswith("11")
            & boundaries["SIGUNGU_NM"].isin(seoul_district_names)
        ].copy()
        boundary_names = set(seoul_boundaries["SIGUNGU_NM"].dropna().unique())

    # 지도의 색상은 데이터의 최신 연월을 포함한 12개 달의 거래 중앙값으로 정합니다.
    latest_month = pd.Period(df["연월"].max(), freq="M")
    first_month_of_recent_year = latest_month - 11
    month_periods = pd.PeriodIndex(df["연월"], freq="M")
    recent_year_data = df.loc[month_periods >= first_month_of_recent_year]
    price_summary = (
        recent_year_data.groupby("자치구명", as_index=False)
        .agg(
            **{
                "최근 1년 ㎡당 전세가격 중앙값": ("㎡당전세가격", "median"),
                "거래 건수": ("㎡당전세가격", "size"),
            }
        )
    )

    # 지도 생성 전에 두 자료의 자치구 이름 목록과 일치 여부를 출력합니다.
    analysis_names = set(price_summary["자치구명"].dropna().unique())
    boundary_only = sorted(boundary_names - analysis_names)
    analysis_only = sorted(analysis_names - boundary_names)
    names_match = boundary_names == analysis_names

    print("\n[서울 자치구 지도 데이터 검증]")
    print(f"서울 자치구 개수(경계): {len(boundary_names)}")
    print(f"분석 데이터 자치구 개수: {len(analysis_names)}")
    print(f"이름이 일치하지 않는 경계 자치구: {boundary_only or '없음'}")
    print(f"이름이 일치하지 않는 분석 자치구: {analysis_only or '없음'}")

    # 경계 25개, 분석 데이터 25개, 이름 완전 일치를 모두 확인해야 지도를 만듭니다.
    if (
        len(boundary_names) != 25
        or len(analysis_names) != 25
        or not names_match
    ):
        raise ValueError(
            "서울 자치구 25개가 모두 이름 기준으로 일치하지 않아 지도를 만들지 않았습니다."
        )

    # 자치구 이름을 키로 가격 요약값을 경계 목록과 연결합니다.
    boundary_table = pd.DataFrame({"SIGUNGU_NM": sorted(boundary_names)})
    map_data = boundary_table.merge(
        price_summary,
        left_on="SIGUNGU_NM",
        right_on="자치구명",
        how="left",
        validate="one_to_one",
    )

    # Shapefile을 사용한 경우에는 EPSG:4326으로 바꾼 뒤 GeoJSON으로 변환합니다.
    if geojson is None:
        seoul_boundaries = seoul_boundaries.to_crs(epsg=4326)
        map_data = seoul_boundaries.merge(
            price_summary,
            left_on="SIGUNGU_NM",
            right_on="자치구명",
            how="left",
            validate="one_to_one",
        )
        geojson = json.loads(map_data.to_json())

    # 25개 가격 값을 경계 GeoJSON과 연결해 Plotly Choropleth Map을 만듭니다.
    map_fig = px.choropleth_map(
        map_data,
        geojson=geojson,
        featureidkey="properties.SIGUNGU_NM",
        locations="SIGUNGU_NM",
        color="최근 1년 ㎡당 전세가격 중앙값",
        custom_data=["거래 건수"],
        color_continuous_scale="YlOrRd",
        center={"lat": 37.5665, "lon": 126.9780},
        zoom=8.5,
        map_style="carto-positron",
        title="서울 자치구별 최근 1년 ㎡당 전세가격 중앙값",
        labels={
            "최근 1년 ㎡당 전세가격 중앙값": "최근 1년 중앙값 (만원/㎡)",
        },
    )
    map_fig.update_traces(
        marker_line_width=0.7,
        marker_line_color="white",
        hovertemplate=(
            "자치구명: %{location}<br>"
            "최근 1년 ㎡당 전세가격 중앙값: %{z:,.2f} 만원/㎡<br>"
            "거래 건수: %{customdata[0]:,}건"
            "<extra></extra>"
        ),
    )
    map_fig.update_layout(margin={"r": 0, "t": 45, "l": 0, "b": 0})
    return map_fig


def main() -> None:
    # 데이터 폴더와 하위 연도 폴더에서 CSV 및 TXT 파일을 찾습니다.
    file_paths = sorted(
        list(DATA_DIR.rglob("*.csv")) + list(DATA_DIR.rglob("*.txt"))
    )

    if not file_paths:
        raise FileNotFoundError(f"데이터 파일을 찾을 수 없습니다: {DATA_DIR}")

    # 연도별 파일을 읽어 하나의 데이터프레임으로 연결합니다.
    dataframes = []
    for file_path in file_paths:
        df_part = read_data_file(file_path)
        dataframes.append(df_part)
        print(f"읽은 파일: {file_path.name} / 행 수: {len(df_part):,}")

    df = pd.concat(dataframes, ignore_index=True)

    # 전처리 전 데이터의 구조를 출력합니다.
    print("\n[전처리 전 데이터 구조]")
    print(f"데이터 크기: {df.shape[0]:,}행, {df.shape[1]:,}열")
    print("전체 컬럼명:")
    print(df.columns.tolist())
    print("\n상위 5행:")
    print(df.head())
    print("\n컬럼별 데이터 타입:")
    print(df.dtypes)
    print("\n컬럼별 결측치 개수:")
    print(df.isna().sum())
    print("\n전월세구분 고유값:")
    print(df["전월세구분"].dropna().unique())
    print("\n자치구명 고유값 개수:")
    print(df["자치구명"].nunique(dropna=True))

    # 전처리 전 주요 컬럼에 실제로 들어 있는 값 예시를 출력합니다.
    print("\n전처리 전 주요 컬럼의 값 예시:")
    for column in ("계약일", "보증금(만원)", "임대면적"):
        print(f"{column}: {df[column].dropna().head(5).tolist()}")

    # 요청한 순서대로 전처리하고, 전처리 후 행 개수를 출력합니다.
    df_clean = preprocess_data(df)

    # 분석용 변수 3개를 추가하고 데이터 최대 계약일 기준 최근 5년만 남깁니다.
    df_analysis = add_analysis_variables_and_filter_recent_years(df_clean)

    # 콘솔에서 분석할 자치구를 하나 입력받습니다. (Streamlit은 사용하지 않습니다.)
    available_districts = sorted(df_analysis["자치구명"].dropna().unique().tolist())
    print("\n분석할 자치구를 선택하세요:")
    print(", ".join(available_districts))
    selected_district = input("자치구명 입력: ").strip()
    if selected_district not in available_districts:
        raise ValueError(
            f"'{selected_district}'은 최근 5년 데이터에 없습니다. "
            "출력된 자치구명 중 하나를 입력해 주세요."
        )

    # 선택한 자치구 데이터에서 법정동 목록을 가져와 동 선택지를 제한합니다.
    available_dongs = get_legal_dongs(df_analysis, selected_district)
    print(f"\n{selected_district}에 존재하는 법정동을 선택하세요:")
    print(", ".join(available_dongs))
    selected_dong = input("법정동명 입력: ").strip()
    if selected_dong not in available_dongs:
        raise ValueError(
            f"'{selected_dong}'은 {selected_district} 데이터에 없습니다. "
            "출력된 법정동명 중 하나를 입력해 주세요."
        )

    # 주요 가격·면적 변수의 분포를 요약하고 그래프로 확인합니다.
    # 이 단계는 분포 점검만 하며 이상치 후보를 자동 제거하지 않습니다.
    inspect_distributions(df_analysis)

    # 서울 전체 월별 집계를 만들고, ㎡당 전세가격 중앙값 추이를 시각화합니다.
    monthly_summary = analyze_monthly_seoul_trend(df_analysis)

    # 선택한 동, 자치구 전체, 서울 전체 추이를 비교합니다.
    # 거래가 적은 동의 월은 중앙값 선을 비워 안정성 문제를 표시합니다.
    location_summary = analyze_dong_trend(
        df_analysis,
        selected_district,
        selected_dong,
    )

    # 선택 자치구와 통계 특성이 가까운 자치구 3곳을 추천합니다.
    similarity_result = recommend_similar_districts(
        df_analysis,
        selected_district,
        top_n=3,
    )
    print("\n[유사 자치구 추천 결과]")
    print(similarity_result["recommendations"].to_string(index=False))
    # 기준 지역과 추천 지역의 실제 feature 값, 표준화 차이, 거리 기여도를 비교합니다.
    verify_similarity_features(similarity_result, selected_district)
    similarity_result["line_fig"].show()

    # 별도 지도 함수가 이름 매칭 검증을 통과한 경우에만 Choropleth를 표시합니다.
    seoul_map = create_seoul_choropleth_map(df_analysis)
    seoul_map.show()

    # 분석에 사용할 데이터와 새 컬럼을 확인합니다.
    # 그래프는 화면에 표시하고, 집계 결과는 콘솔에 출력합니다.
    print("\n최근 5년 분석 데이터 상위 5행:")
    print(df_analysis.head())
    print("\n전처리 후 핵심 컬럼 데이터 타입:")
    print(df_analysis[CORE_COLUMNS + ["연도", "연월", "㎡당전세가격"]].dtypes)


if __name__ == "__main__":
    main()

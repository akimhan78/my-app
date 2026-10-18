"""서울 전세가격 대시보드의 첫 번째 화면: 지역별 전세 추이."""

from pathlib import Path

import pandas as pd
import streamlit as st

import analysis


# 원본 연도별 파일과 경계 파일의 위치를 이 앱 파일 기준으로 찾습니다.
APP_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="서울 전세가격 분석",
    page_icon="🏠",
    layout="wide",
)

# 화면 전체의 배경, 카드, 탭 간격을 맞춰 대시보드를 한눈에 읽기 쉽게 합니다.
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] { background: #f5f7fb; }
    [data-testid="stHeader"] { background: rgba(245, 247, 251, 0.88); }
    .block-container { max-width: 1480px; padding-top: 1.6rem; padding-bottom: 3rem; }
    [data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #e4eaf2; border-radius: 14px;
        padding: 1rem 1.1rem; box-shadow: 0 3px 12px rgba(23, 43, 77, 0.04);
    }
    [data-testid="stPlotlyChart"] {
        background: #ffffff; border: 1px solid #e4eaf2; border-radius: 14px;
        padding: 0.35rem;
    }
    [data-baseweb="tab-list"] { gap: 0.45rem; border-bottom: 1px solid #e2e8f0; }
    [data-baseweb="tab"] { border-radius: 10px 10px 0 0; padding: 0.65rem 1.1rem; }
    [data-baseweb="tab"][aria-selected="true"] { background: #e8f0ff; }
    [data-testid="stSelectbox"] { background: #ffffff; border-radius: 10px; }
    h1, h2, h3 { letter-spacing: -0.025em; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="최근 5년 전세 데이터를 불러오고 있습니다...")
def load_analysis_data() -> pd.DataFrame:
    """배포용 gzip 또는 로컬 원본을 읽고 기존 분석용 처리를 적용합니다."""
    # 저장소에는 용량을 줄인 gzip 파일을 두고, 로컬 폴더에는 원본을 그대로 둘 수 있습니다.
    deploy_files = sorted((APP_DIR / "deployment_data").glob("*.gz"))
    data_files = deploy_files or sorted(
        list(APP_DIR.rglob("*.csv")) + list(APP_DIR.rglob("*.txt"))
    )
    if not data_files:
        raise FileNotFoundError(f"데이터 파일이 없습니다: {APP_DIR}")

    # 여러 해의 원본 파일을 읽어 하나의 표로 합칩니다.
    raw_data = pd.concat(
        [analysis.read_data_file(path) for path in data_files],
        ignore_index=True,
    )

    # analysis.py의 기존 전처리와 분석용 변수 생성 함수를 재사용합니다.
    cleaned_data = analysis.preprocess_data(raw_data)
    return analysis.add_analysis_variables_and_filter_recent_years(cleaned_data)


@st.cache_resource(show_spinner="서울 자치구 지도를 준비하고 있습니다...")
def load_seoul_map():
    """검증된 서울 자치구 Choropleth Figure를 한 번 만들어 재사용합니다."""
    return analysis.create_seoul_choropleth_map(load_analysis_data())


def format_metric(value, suffix: str = "", decimals: int = 2) -> str:
    """숫자 metric을 보기 좋게 표시하고, 계산할 수 없는 값은 안내합니다."""
    if pd.isna(value):
        return "계산 불가"
    if decimals == 0:
        return f"{int(value):,}{suffix}"
    return f"{value:,.{decimals}f}{suffix}"


def style_chart(figure):
    """그래프마다 같은 글꼴, 여백, 격자 색을 적용해 화면을 정돈합니다."""
    figure.update_layout(
        font={"family": "Arial, Malgun Gothic, sans-serif", "color": "#263246"},
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin={"l": 24, "r": 24, "t": 72, "b": 32},
        hoverlabel={"bgcolor": "#172b4d", "font_color": "white"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    figure.update_xaxes(showgrid=False, zeroline=False, linecolor="#d9e1ec")
    figure.update_yaxes(
        showgrid=True,
        gridcolor="#edf1f6",
        zeroline=False,
        linecolor="#d9e1ec",
    )
    return figure


st.title("서울 전세가격 분석")
st.caption(
    "대표 가격 지표는 월별 ㎡당 전세가격 중앙값입니다. "
    "기간은 데이터의 가장 최근 계약일을 기준으로 최근 5년을 산정합니다."
)

trend_tab, compare_tab, similar_tab = st.tabs(
    ["지역별 전세 추이", "두 지역 비교", "유사 지역 찾기"]
)

with trend_tab:
    st.header("지역별 전세 추이")
    st.caption("데이터에 포함된 가장 최근 계약일을 기준으로 최근 5년을 분석합니다.")

    with st.spinner("분석 데이터를 준비하고 있습니다..."):
        try:
            df_analysis = load_analysis_data()
        except Exception as error:
            st.error(f"분석 데이터를 불러오지 못했습니다: {error}")
            st.stop()

    latest_contract_date = df_analysis["계약일"].max()
    start_date = latest_contract_date - pd.DateOffset(years=5)
    st.caption(
        f"분석 기간: {start_date:%Y-%m-%d} ~ {latest_contract_date:%Y-%m-%d}"
    )

    # 첫 화면에는 지도와 지역 선택 상자를 나란히 배치합니다.
    map_column, selector_column = st.columns([1.65, 1])

    with map_column:
        st.subheader("자치구별 최근 1년 가격")
        try:
            map_figure = load_seoul_map()
            st.plotly_chart(map_figure, use_container_width=True)
        except Exception as error:
            st.error(f"서울 자치구 지도를 만들지 못했습니다: {error}")

    with selector_column:
        st.subheader("분석 지역 선택")
        districts = sorted(df_analysis["자치구명"].dropna().unique().tolist())
        selected_district = st.selectbox("자치구", districts, key="trend_district")

        # 선택한 자치구의 법정동만 두 번째 선택 상자에 표시합니다.
        legal_dongs = analysis.get_legal_dongs(df_analysis, selected_district)
        selected_dong = st.selectbox(
            "법정동",
            legal_dongs,
            key=f"trend_dong_{selected_district}",
        )

    # 기존 동·자치구·서울 비교 함수를 호출하되, Figure는 Streamlit에서 표시합니다.
    try:
        trend_result = analysis.analyze_dong_trend(
            df_analysis,
            selected_district,
            selected_dong,
            show_plot=False,
            verbose=False,
        )
    except Exception as error:
        st.error(f"선택한 지역의 추이를 계산하지 못했습니다: {error}")
        st.stop()

    st.subheader(f"{selected_district} {selected_dong} 주요 통계")
    dong_metrics = trend_result["dong_summary"]
    metric_columns = st.columns(5)
    metric_columns[0].metric(
        "최근 유효월 ㎡당 가격 중앙값",
        format_metric(dong_metrics["최근 가격 수준(만원/㎡)"], " 만원/㎡"),
    )
    metric_columns[1].metric(
        "최근 1년 가격 변화율",
        format_metric(dong_metrics["최근 1년 가격 변화율(%)"], "%"),
    )
    metric_columns[2].metric(
        "최근 5년 가격 변화율",
        format_metric(dong_metrics["최근 5년 가격 변화율(%)"], "%"),
    )
    metric_columns[3].metric(
        "월별 가격 변동성",
        format_metric(dong_metrics["월별 가격 변동성(%)"], "%"),
    )
    metric_columns[4].metric(
        "전체 거래 건수",
        format_metric(dong_metrics["거래 건수"], "건", decimals=0),
    )

    st.caption(
        "동의 월별 가격은 거래 5건 미만인 달을 그래프와 변화율·변동성 계산에서 제외합니다. "
        "전체 거래 건수 metric에는 해당 월 거래도 포함됩니다."
    )

    st.subheader("선택한 동 · 자치구 전체 · 서울 전체")
    st.plotly_chart(style_chart(trend_result["line_fig"]), use_container_width=True)

    # 실제 월 집계에서 최고·최저를 찾아 그래프에서 확인할 수 있는 해석을 덧붙입니다.
    stable_months = trend_result["dong_monthly"].loc[
        trend_result["dong_monthly"]["거래 건수"] >= 5
    ]
    if not stable_months.empty:
        high_month = stable_months.loc[
            stable_months["㎡당 전세가격 중앙값"].idxmax()
        ]
        low_month = stable_months.loc[
            stable_months["㎡당 전세가격 중앙값"].idxmin()
        ]
        st.info(
            f"그래프 읽기 · {selected_dong}의 거래 5건 이상 월 중 "
            f"중앙값은 {high_month['연월']}에 가장 높았습니다 "
            f"({high_month['㎡당 전세가격 중앙값']:,.2f}만원/㎡). "
            f"가장 낮은 달은 {low_month['연월']} "
            f"({low_month['㎡당 전세가격 중앙값']:,.2f}만원/㎡)이며, "
            f"두 시점 차이는 "
            f"{high_month['㎡당 전세가격 중앙값'] - low_month['㎡당 전세가격 중앙값']:,.2f}만원/㎡입니다."
        )


with compare_tab:
    st.header("두 지역 비교")
    st.caption("두 자치구의 최근 5년 월별 전세가격과 주요 통계를 비교합니다.")

    # A와 B가 같은 자치구로 선택되지 않도록 B 선택 목록에서 A를 제외합니다.
    district_names = sorted(df_analysis["자치구명"].dropna().unique().tolist())
    if len(district_names) < 2:
        st.warning("비교할 자치구가 두 곳 이상 있어야 합니다.")
    else:
        selector_a, selector_b = st.columns(2)
        with selector_a:
            district_a = st.selectbox(
                "자치구 A",
                district_names,
                key="compare_district_a",
            )
        district_b_options = [name for name in district_names if name != district_a]
        with selector_b:
            district_b = st.selectbox(
                "자치구 B",
                district_b_options,
                key="compare_district_b",
            )

        # 기존 compare_districts 함수가 집계표와 Plotly Figure를 반환합니다.
        try:
            comparison = analysis.compare_districts(
                df_analysis,
                district_a,
                district_b,
            )
        except Exception as error:
            st.error(f"두 자치구를 비교하지 못했습니다: {error}")
        else:
            st.subheader("주요 통계 비교")
            st.dataframe(
                comparison["summary"],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "지역": st.column_config.TextColumn("자치구"),
                    "최근 가격 수준(만원/㎡)": st.column_config.NumberColumn(
                        "현재 가격 수준 (만원/㎡)", format="%,.2f"
                    ),
                    "최근 1년 가격 변화율(%)": st.column_config.NumberColumn(
                        "1년 변화율 (%)", format="%.2f"
                    ),
                    "최근 5년 가격 변화율(%)": st.column_config.NumberColumn(
                        "5년 변화율 (%)", format="%.2f"
                    ),
                    "월별 가격 변동성(%)": st.column_config.NumberColumn(
                        "월별 변동성 (%)", format="%.2f"
                    ),
                    "거래 건수": st.column_config.NumberColumn(
                        "거래 건수", format="%,d"
                    ),
                },
            )

            st.subheader("최근 5년 월별 가격 추이")
            st.plotly_chart(style_chart(comparison["line_fig"]), use_container_width=True)

            # 선택한 두 자치구의 집계 결과로 가격 수준과 장기 변화 차이를 요약합니다.
            summary = comparison["summary"].set_index("지역")
            price_gap = (
                summary.loc[district_a, "최근 가격 수준(만원/㎡)"]
                - summary.loc[district_b, "최근 가격 수준(만원/㎡)"]
            )
            change_gap = (
                summary.loc[district_a, "최근 5년 가격 변화율(%)"]
                - summary.loc[district_b, "최근 5년 가격 변화율(%)"]
            )
            higher_district = district_a if price_gap >= 0 else district_b
            st.info(
                f"그래프 읽기 · 최근 가격 중앙값은 {higher_district}가 "
                f"{abs(price_gap):,.2f}만원/㎡ 더 높습니다. "
                f"5년 변화율의 A-B 차이는 {change_gap:+.2f}%p입니다. "
                "월별 선 그래프와 아래 지표별 그래프에서 기간 중 변화를 함께 확인하세요."
            )

            st.subheader("두 자치구 주요 지표 그래프 비교")
            st.plotly_chart(style_chart(comparison["bar_fig"]), use_container_width=True)


with similar_tab:
    st.header("유사 지역 찾기")
    st.caption(
        "최근 1년 가격 수준, 최근 5년 변화율, 월별 변동성을 표준화하고 "
        "Euclidean Distance로 가까운 자치구를 찾습니다."
    )

    # 추천 기준 지역은 현재 분석 데이터에 포함된 자치구에서 고릅니다.
    district_names = sorted(df_analysis["자치구명"].dropna().unique().tolist())
    reference_district = st.selectbox(
        "기준 자치구",
        district_names,
        key="similarity_reference_district",
    )

    # 기존 추천 함수가 통계, TOP 3 표, 가격 추이 그래프를 계산합니다.
    try:
        similarity_result = analysis.recommend_similar_districts(
            df_analysis,
            reference_district,
            top_n=3,
        )
    except Exception as error:
        st.error(f"유사 자치구를 계산하지 못했습니다: {error}")
    else:
        recommendations = similarity_result["recommendations"]
        features = similarity_result["features"].set_index("자치구명")
        feature_labels = {
            "최근 1년 ㎡당 전세가격 중앙값": "최근 1년 가격 중앙값 (만원/㎡)",
            "최근 5년 가격 변화율": "최근 5년 가격 변화율 (%)",
            "월별 가격 변동성": "월별 가격 변동성 (%)",
        }

        st.subheader(f"기준 지역: {reference_district}")
        reference_values = features.loc[reference_district]
        metric_columns = st.columns(3)
        metric_columns[0].metric(
            "최근 1년 ㎡당 전세가격 중앙값",
            format_metric(reference_values["최근 1년 ㎡당 전세가격 중앙값"]),
        )
        metric_columns[1].metric(
            "최근 5년 가격 변화율",
            format_metric(reference_values["최근 5년 가격 변화율"], "%"),
        )
        metric_columns[2].metric(
            "월별 가격 변동성",
            format_metric(reference_values["월별 가격 변동성"], "%"),
        )

        st.subheader("추천 지역 TOP 3")
        st.dataframe(
            recommendations,
            hide_index=True,
            use_container_width=True,
            column_config={
                "추천 순위": st.column_config.NumberColumn("순위", format="%d위"),
                "자치구명": st.column_config.TextColumn("추천 자치구"),
                "거리값": st.column_config.NumberColumn("거리값", format="%.4f"),
                "최근 1년 ㎡당 전세가격 중앙값(만원/㎡)": st.column_config.NumberColumn(
                    "최근 1년 가격 중앙값 (만원/㎡)", format="%,.2f"
                ),
                "최근 5년 가격 변화율(%)": st.column_config.NumberColumn(
                    "최근 5년 가격 변화율 (%)", format="%.2f"
                ),
                "월별 가격 변동성(%)": st.column_config.NumberColumn(
                    "월별 가격 변동성 (%)", format="%.2f"
                ),
            },
        )

        # 기준 지역과 추천 지역의 원래 통계값을 한 표에서 직접 비교합니다.
        comparison_rows = [
            {
                "구분": "기준 지역",
                "자치구명": reference_district,
                "거리값": None,
                **reference_values.to_dict(),
            }
        ]
        for _, recommendation in recommendations.iterrows():
            district = recommendation["자치구명"]
            comparison_rows.append(
                {
                    "구분": f"추천 {int(recommendation['추천 순위'])}위",
                    "자치구명": district,
                    "거리값": recommendation["거리값"],
                    **features.loc[district].to_dict(),
                }
            )
        feature_comparison = pd.DataFrame(comparison_rows).rename(
            columns=feature_labels
        )

        st.subheader("기준 지역과 추천 지역 통계 비교")
        st.dataframe(
            feature_comparison,
            hide_index=True,
            use_container_width=True,
            column_config={
                "구분": st.column_config.TextColumn("구분"),
                "자치구명": st.column_config.TextColumn("자치구"),
                "거리값": st.column_config.NumberColumn("거리값", format="%.4f"),
                "최근 1년 가격 중앙값 (만원/㎡)": st.column_config.NumberColumn(
                    "최근 1년 가격 중앙값 (만원/㎡)", format="%,.2f"
                ),
                "최근 5년 가격 변화율 (%)": st.column_config.NumberColumn(
                    "최근 5년 가격 변화율 (%)", format="%.2f"
                ),
                "월별 가격 변동성 (%)": st.column_config.NumberColumn(
                    "월별 가격 변동성 (%)", format="%.2f"
                ),
            },
        )

        st.subheader("기준 지역과 추천 지역의 최근 5년 가격 추이")
        st.plotly_chart(style_chart(similarity_result["line_fig"]), use_container_width=True)

        # 유사도 점수와 실제 원 단위 통계 차이를 함께 보여 추천 기준을 설명합니다.
        closest = recommendations.iloc[0]
        closest_values = features.loc[closest["자치구명"]]
        st.info(
            f"그래프 읽기 · 기준 지역과 가장 가까운 곳은 {closest['자치구명']}이며 "
            f"표준화 Euclidean Distance는 {closest['거리값']:.4f}입니다. "
            f"최근 1년 가격 중앙값 차이는 "
            f"{abs(reference_values['최근 1년 ㎡당 전세가격 중앙값'] - closest_values['최근 1년 ㎡당 전세가격 중앙값']):,.2f}만원/㎡, "
            f"5년 변화율 차이는 "
            f"{abs(reference_values['최근 5년 가격 변화율'] - closest_values['최근 5년 가격 변화율']):.2f}%p, "
            f"월별 변동성 차이는 "
            f"{abs(reference_values['월별 가격 변동성'] - closest_values['월별 가격 변동성']):.2f}%p입니다."
        )

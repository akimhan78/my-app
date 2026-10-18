# 서울 전세가격 분석 대시보드

서울시 전세 계약 데이터를 이용해 최근 5년 가격 흐름을 살펴보는 Streamlit 프로젝트입니다.

## 기능

- 자치구 및 법정동의 월별 ㎡당 전세가격 중앙값 추이와 서울 전체 비교
- 두 자치구의 가격 흐름과 요약 통계 비교
- 최근 가격 수준, 5년 변화율, 월별 변동성을 이용한 유사 자치구 추천
- 최근 1년 ㎡당 전세가격 중앙값 Choropleth 지도

최근 5년의 시작점은 오늘 날짜가 아니라 데이터의 가장 최근 계약일을 기준으로 정합니다.

## 로컬 실행

Python 3.12 이상을 권장합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

`deployment_data/`에는 GitHub와 컨테이너 배포용 압축 데이터 및 서울 구 경계 GeoJSON이 있습니다. 원본 파일을 사용할 경우 앱 폴더 아래 연도별 폴더에 CSV 또는 TXT 파일을 둘 수 있습니다.

## GitHub 및 Cloudflare 배포

이 저장소는 Cloudflare Workers Builds에서 `npm install` 후 `npx wrangler deploy`를 실행하도록 구성했습니다. Cloudflare Dashboard에서 이 GitHub 저장소를 Worker Builds에 연결하고 production branch를 `main`으로 지정하세요.

Cloudflare Containers는 실행 중인 Streamlit 서버를 제공하므로 정적 Pages 배포와 다릅니다. Cloudflare 계정에서 Workers Paid 플랜 및 Containers 사용이 가능해야 합니다. 첫 배포 후 컨테이너가 준비되기까지 몇 분이 걸릴 수 있습니다.

## 데이터 및 비밀 정보

- 배포용 거래 데이터는 `.gz` 파일로 Git에 포함됩니다. 저장소 공개 범위를 결정할 때 데이터 배포 권한과 과제 요구사항을 먼저 확인하세요.
- 원본 연도별 CSV/TXT, `.env`, API key, Streamlit secrets, Python 환경은 Git에서 제외됩니다.
- 경계 데이터는 서울 25개 구만 포함한 EPSG:4326 GeoJSON으로 축소해 포함합니다.


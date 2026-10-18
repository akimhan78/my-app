# 서울 전세 인사이트

서울시 전세 계약을 자치구와 법정동별로 살펴보는 Cloudflare Pages 정적 대시보드입니다. 앱은 별도 서버 없이 브라우저에서 실행되며, Plotly로 지도와 그래프를 표시합니다.

## 포함 기능

- 자치구 지도와 자치구·법정동별 월간 가격 추이
- 두 자치구의 가격 추이와 주요 통계 비교
- 세 가지 통계 특성을 표준화한 유클리드 거리 기반 유사 자치구 TOP 3
- 데이터의 가장 최근 계약일을 기준으로 한 최근 5년 분석

대표 가격 지표는 `㎡당 전세가격 중앙값`입니다. 법정동의 월 거래가 5건보다 적으면 그 달의 가격을 추이 그래프와 동 요약 지표에서 제외합니다. 실제 거래 건수와 전체 거래 수에는 소량 거래 월도 포함합니다.

## 프로젝트 파일

- `public/`: Pages가 게시하는 HTML, CSS, JavaScript, 압축 집계 데이터
- `scripts/build_static_data.py`: 연도별 원본 자료에서 정적 대시보드용 월별 자료를 다시 생성
- `deployment_data/`: 정적 집계 자료를 만들기 위한 원본 압축 CSV/TXT 및 자치구 GeoJSON
- `analysis.py`: 기존 pandas/Plotly 분석 코드 참고용

정적 사이트에는 원본 거래 행을 게시하지 않습니다. 대시보드는 자치구·법정동별 월간 중앙값과 건수로 집계된 자료만 내려받습니다.

## 로컬에서 보기

`public/index.html`은 정적 파일이므로 로컬 HTTP 서버로 열어야 압축 자료를 읽을 수 있습니다.

```powershell
python -m http.server 8000 --directory public
```

브라우저에서 `http://localhost:8000`을 엽니다. Plotly.js는 CDN에서 가져오므로 그래프를 보려면 인터넷 연결이 필요합니다.

## 집계 자료 다시 만들기

프로젝트 루트에서 pandas가 설치된 Python 환경을 사용합니다.

```powershell
pip install -r requirements.txt
python scripts/build_static_data.py
```

스크립트는 `deployment_data/*.gz`를 읽어 `public/data/dashboard.json.gz`를 다시 만듭니다. 새 데이터로 갱신한 경우 이 생성 파일을 Git에 반영해 Pages에 배포합니다.

## Cloudflare Pages 배포

저장소를 GitHub에 push한 다음 Cloudflare Dashboard에서 **Workers & Pages → Create application → Pages → Connect to Git**으로 저장소를 연결합니다.

- Production branch: `main`
- Build command: 비워 둠
- Build output directory: `public`
- Root directory: 저장소 루트

`wrangler.jsonc`에는 Pages 출력 폴더가 설정되어 있습니다. Cloudflare 계정에 Wrangler 로그인이 되어 있다면 명령줄 배포도 가능합니다.

```powershell
npm install
npm run deploy
```

## 해석 시 참고

최근 1년 자치구 가격 특성은 최근 12개월 계약 원자료의 ㎡당 전세가격 중앙값입니다. 월별 추이와 변화율·변동성은 월별 중앙값을 사용합니다. 유사도 계산은 최근 1년 중앙값, 최근 5년 변화율, 월별 변동성을 각각 z-score로 표준화한 후 동일한 비중으로 유클리드 거리를 계산합니다.

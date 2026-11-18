# tide-kr-data

물때(Tide KR) 워치 앱이 읽는 조석·관측 자료 사본. GitHub Actions가 공공데이터포털(국립해양조사원)에서 받아 저장합니다.

- `data/tide/<관측소>.json` — 조석예보(고·저조), 어제~5일 뒤. 매일 04:17 KST 갱신
- `data/obs/<관측소>.json` — 최신 관측(수온·기온·바람). 매시 갱신
- 수집: `scripts/fetch.py`, 관측소 목록: `scripts/stations.json` (앱 `shared/stations.js`와 같게 유지)

## 처음 설정
1. Settings → Secrets and variables → Actions → New repository secret
   - Name: `KHOA_KEY` / Value: 공공데이터포털 일반 인증키
2. Actions 탭 → update-data → Run workflow (what: both) 로 첫 자료 만들기

자료 출처: 국립해양조사원(공공누리 제1유형)

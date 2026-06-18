# XAUUSD 돌파 + KTR 그리드 전략 백테스트

골드(XAUUSD) 및 FX 메이저의 **볼린저밴드 돌파 + KTR 그리드(물타기) 전략**을 Dukascopy MID 데이터로 백테스트·고도화하는 프로젝트.

> 전략 상세·확정안·핵심 발견은 [`CLAUDE.md`](CLAUDE.md)와 `2020_2026/report.html`(브라우저로 열기) 참조.

## 1차 결론 요약 (골드 2020~2026)
실거래 룰(한 번에 그리드 1개 · KST 08~24시 진입 · 체결비용) 적용 시 **10분봉만 견고**.
- **10m v1**: 연복리 +18.7%, MDD 14.9%, 승률 93.5%
- 10m v2(보수형): +10.7%, MDD 9.5%
- 2m/5m: 체결비용으로 사망/한계

확정 전략: **10분봉 · v1 · 후방 랏 1·1·2·2·3·4 · TP 1.5KTR · 6차 · 반등탈출 · 리스크 2~3% · 08~24시 · 순차 · 필터 없음.**

## 요구 환경
- **Python 3** — 분석 스크립트. **표준 라이브러리만 사용 → `pip install` 불필요.**
- **Node.js** — 데이터 수집(fetch)에만 필요.

## 빠른 시작 (다른 PC에서 이어가기)
```bash
git clone <repo>
cd <repo>/2020_2026/fetch_node
npm install            # dukascopy-node 설치 (node_modules는 .gitignore)
```

### 데이터 준비 — 둘 중 하나
**A) 재생성 (옮길 것 없음, 수 시간 소요)**
```bash
node run_fetch.mjs     # 골드+FX 전체 수집 → 병합 → 검증. parts 있으면 skip(resume)
```
**B) 운반 (빠름)**
- 받아둔 CSV(또는 `parts/` 폴더)를 클라우드/USB로 옮겨 배치.
  - 최종 CSV → `2020_2026/`
  - 미병합 parts → `2020_2026/fetch_node/parts/` 후 `node run_fetch.mjs` (skip+병합)
- **팁**: 분석은 2m/5m/10m만 사용(1m 미사용). **확정 전략이 10분봉이라 `*_10m_*.csv`만 있으면 충분**(인스트루먼트당 ~14~32MB). CSV는 zip 시 ~3.5~3.9배 압축.

### 분석 실행
```bash
cd 2020_2026
python scripts/45_report.py        # report.html 재생성
python scripts/47_chart_viewer.py  # fail_charts.html 재생성
# (스크립트는 2020_2026 디렉토리에서 실행, 입출력은 상대경로)
```

## 데이터 파일 규칙
`{instrument}_{tf}_{start}_{end}.csv`, 헤더 `time,open,high,low,close,volume` (BOM), `time`=epoch초, 가격=MID.
- 골드(1차): `xauusd_{1m,2m,5m,10m}_2020-01-01_2026-06-16.csv`
- 확장(2차): `eurusd/gbpusd/usdjpy_{tf}_2010-01-01_2026-06-16.csv`, `xauusd_{tf}_2010-01-01_2019-12-31.csv`
- **모든 CSV는 `.gitignore`** (최대 313MB, GitHub 100MB 제한 초과).

## 디렉토리
```
2020_2026/
  scripts/      분석 파이프라인 (.py, 표준 라이브러리만)
  fetch_node/   Dukascopy 수집 (fetch_inst.mjs / run_fetch.mjs / merge_inst.mjs)
  *.html        report.html(종합), fail_charts.html(실패 멀티TF 뷰어) 등
CLAUDE.md       프로젝트 컨텍스트 (Claude 자동 로드 — 협업 맥락 이동 수단)
README.md       이 문서
```

## 협업/지속 워크플로
- 개선 아이디어마다 **브랜치 → PR**.
- 다른 PC: clone → npm install → 데이터(재생성 또는 운반) → 스크립트 실행 → 개선 → push.
- AI 협업 이어가기: 새 PC에서 Claude를 repo에서 열면 **`CLAUDE.md`를 자동 로드**해 맥락을 이어받음.

## 면책
과거 데이터 기반 백테스트이며 미래 수익을 보장하지 않습니다.

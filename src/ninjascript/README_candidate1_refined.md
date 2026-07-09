# Candidate1RefinedXauusd NinjaTrader 8 사용법

## 파일

- `Candidate1RefinedXauusd.cs`

NinjaTrader 8에서 아래 폴더로 복사합니다.

```text
Documents\NinjaTrader 8\bin\Custom\Strategies\Candidate1RefinedXauusd.cs
```

NinjaTrader에서 `New > NinjaScript Editor`를 열고 컴파일합니다.

## 권장 백테스트 차트

- 상품: XAUUSD / Gold CFD
- 기본 차트 주기: 5 Minute
- 추가 시리즈는 전략이 자동 추가:
  - 2 Minute: Onebee 보조 신호
  - 1 Day: 월 필터

## 전략 구성

- 월 필터:
  - `Ret20 Min = 0.0084`
  - `Ret240 Min = -0.0428`
  - `ADR20 Min Points = 18`
- 일 손실 제한:
  - `Daily Stop Points = 50`
- Grid:
  - KST 09:00~18:00
  - 3단 진입, 10P 간격
  - 35P 하드스탑
  - 10P arm / 10P trail
  - 3차 진입 후 평균가 +3P 회복 시 50% 축소
- Session:
  - Asia / Europe / NewYork 세션 첫 15분 범위
  - body ratio 0.90 이상 돌파 후 리테스트
  - 목표 2R
- Onebee:
  - 2분봉 SMA20/120 cycle
  - 60봉 박스 돌파 후 BB4/4 터치
  - NinjaScript 포팅본에서는 session KTR 대신 ATR proxy 사용

## 리포트 출력

전략 종료 시 아래 폴더에 CSV가 생성됩니다.

```text
Documents\NinjaTrader 8\Candidate1RefinedReports\
```

생성 파일:

- `candidate1_yearly_YYYYMMDD_HHMMSS.csv`
- `candidate1_monthly_YYYYMMDD_HHMMSS.csv`

## 주의

Python 백테스트가 권위본입니다.

NinjaTrader 전략은 실제 플랫폼 백테스트용 포팅본이며, 브로커의 XAUUSD 데이터 시간대, 거래 시간, 스프레드/커미션, point value 설정에 따라 결과가 달라질 수 있습니다.

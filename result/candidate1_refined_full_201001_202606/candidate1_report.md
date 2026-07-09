# Candidate 1 Refined Full Backtest

## Rule
- Monthly filter: ret20 >= 0.0084, ret240 >= -0.0428, adr20 >= 18.0P.
- Grid: Strategy2 5m r2, KST 09:00-18:00, arm 10P, trail 10P, third-fill +3P / 50% reduce.
- Session: body090 5m session retest.
- Onebee: 2m SMA cross box Onebee KTR.
- Duplicate same entry time + direction: grid > session > onebee.
- Day stop: stop new entries for the KST day after cumulative day net <= -50P.

## Headline
- Active months: 40
- Active days: 1035
- Trades: 2071
- Trades per active day: 2.001
- Net: 4335.0P
- Average: 2.093P
- PF: 1.371
- MDD: 983.6P
- Positive/negative months: 29/11

## Cost Sensitivity
- Extra +0.3P/unit: net 3561.0P, avg 1.719P, PF 1.296, MDD 1008.8P.
- Extra +1.0P/unit: net 1755.0P, PF 1.136.

## Caveat
This is a practical candidate, not a guarantee. 2011 remains negative, and the 2025-12 month is still the worst single active month.

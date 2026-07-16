# INVALIDATED: UTC-Calendar Robust-Length Holdout

> This holdout used UTC calendar bars containing short Sunday partial candles. A later boundary audit invalidated its SMA60 robustness claim. See `result/ny17_daily_king_sma50/REPORT.md` for the corrected NY17 result.

Selection data: 2010-2018 only.
For each MA length, all 25 combinations of TR length and band width are tested across three training chunks.
Eligible MA lengths require 25/25 combinations to be profitable in every training chunk.
The slowest eligible length is selected to minimize turnover under fixed trading cost; TR40 and band 1.0 are central defaults.

Selected config: SMA 60, simple TR 40, band 1.00.
Training: 102 trades, net 448.42, PF 1.3154.
Unseen 2019-2026 holdout: 88 trades, net 1966.55, PF 2.1346, DD 303.14.
Positive holdout chunks: 3/3.
Holdout frequency: 0.0379 trades per trading day.

The holdout does not participate in parameter selection.
Caveat: this robustness selection rule was formulated during the current full-history research process, so only future data can provide pristine prospective confirmation.

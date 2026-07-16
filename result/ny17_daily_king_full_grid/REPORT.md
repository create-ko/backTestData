# NY17 Daily King Keltner Full Grid

All 200 configurations use New York 17:00 trading-day bars built from 5m data.

 ma_length  configs  train_3of3  holdout_3of3  full_6of6  median_pf  median_worst_chunk
        20       25           0             1          0     1.1092           -158.5584
        30       25          25             9          9     1.3898            -63.0666
        40       25          24             0          0     1.5189            -97.7540
        50       25          25            25         25     1.8042             44.7038
        60       25           4             3          1     1.9616           -127.2135
        80       25           0             8          0     2.2315           -594.3993
       100       25           0             0          0     1.8302           -243.3337
       120       25           0             0          0     2.1191           -123.1479

Six-of-six configurations: 35/200.
Training-only robust-length rule selected: SMA 50, TR 40, band 1.00.
Unseen holdout: 79 trades, net 1919.43, PF 2.0487.
Selected config holdout chunks: 3/3.

The legacy UTC partial-bar results are not used in this grid.

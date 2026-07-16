# Daily King Keltner Boundary Sensitivity

The SMA60 / simple TR40 / 1ATR candidate is rebuilt from 5m data under multiple daily boundaries.
New York 17:00 and KST 07:00/08:00 boundaries merge the Sunday open into the following trading session.
UTC-calendar raw preserves the legacy short Sunday partial bars for comparison.

        boundary  daily_bars  short_bars_under_100  trades  net_points  profit_factor  max_drawdown  positive_chunks  worst_chunk_net  holdout_trades  holdout_net  holdout_pf  chunk_1_net  chunk_2_net  chunk_3_net  chunk_4_net  chunk_5_net  chunk_6_net
       utc00_raw        5122                   873     190   2414.9671         1.7654      432.9035                6          44.6547              88    1966.5466      2.1346      94.8628     105.3374     248.2203      44.6547     396.7171    1525.1748
utc00_drop_short        4249                     0     151   2306.3050         1.9299      463.2591                4        -413.4504              63    2063.7207      2.8887     530.1010    -413.4504     125.9337    -124.5430     533.1376    1655.1261
            ny17        4256                     7     152   2533.8462         2.0072      521.9435                4        -117.7604              62    2395.8259      3.1928     138.9483     -63.2372      62.3092    -117.7604     524.1023    1989.4840
 ny17_drop_short        4249                     0     151   2568.7333         2.0236      520.8691                4        -413.9373              62    2401.9809      3.1984     518.3805    -413.9373      62.3092    -117.7604     524.1023    1995.6390
           kst07        4357                   108     152   2571.7597         2.0069      526.7400                4        -117.7604              62    2395.8259      3.1928     181.6855     -68.0599      62.3082    -117.7604     524.1023    1989.4840
           kst08        4858                   609     183   2086.5629         1.6023      496.2018                5        -216.0820              80    1809.8020      1.9152     141.3931       0.1548     135.2131    -216.0820     472.2726    1553.6114
           kst00        5125                   875     179   2650.2849         1.8697      484.6700                6          40.5835              81    2239.0521      2.3866      58.2157     138.4413     214.5757      40.5835     577.9525    1620.5161

        boundary  configs  six_chunk_configs  median_pf  minimum_worst_chunk
           kst00       25                 12     1.7959             -63.4357
           kst07       25                  1     1.9196            -234.9919
           kst08       25                  0     1.6288            -235.4945
            ny17       25                  1     1.9616            -234.9919
 ny17_drop_short       25                  0     1.9849            -468.7517
utc00_drop_short       25                  0     1.8958            -447.7897
       utc00_raw       25                 25     1.7730               6.3447

A TradingView-ready strategy requires stability on session-based daily bars, not only legacy UTC calendar bars.

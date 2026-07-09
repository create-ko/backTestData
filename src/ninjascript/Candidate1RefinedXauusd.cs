#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

// NinjaTrader 8 Strategy port of Candidate 1 Refined.
//
// Authoritative research result:
//   backTestData/src/scripts/98_candidate1_refined_full_backtest.py
//
// Recommended chart:
//   XAUUSD / Gold CFD, primary series = 5 minute.
//
// This strategy adds:
//   BIP 1 = 2 minute for Onebee approximation
//   BIP 2 = Daily for the monthly regime filter
//
// It intentionally keeps the implementation self-contained so it can be copied into:
//   Documents\NinjaTrader 8\bin\Custom\Strategies\Candidate1RefinedXauusd.cs

namespace NinjaTrader.NinjaScript.Strategies
{
    public class Candidate1RefinedXauusd : Strategy
    {
        private const int PrimaryBars = 0;
        private const int TwoMinuteBars = 1;
        private const int DailyBars = 2;

        private readonly Dictionary<int, bool> regimeByMonth = new Dictionary<int, bool>();
        private readonly Dictionary<int, ReportBucket> yearly = new Dictionary<int, ReportBucket>();
        private readonly Dictionary<int, ReportBucket> monthly = new Dictionary<int, ReportBucket>();

        private TimeZoneInfo kstZone;
        private TimeZoneInfo londonZone;
        private TimeZoneInfo newYorkZone;

        private int lastTradeCount;
        private int currentKstDayKey;
        private double dayPnl;

        private int gridDir;
        private int gridBarsLeft;
        private double gridEntry1;
        private double gridStopPrice;
        private bool gridReduced;
        private bool gridTrailing;
        private double gridTrailStop;

        private double sessionHigh;
        private double sessionLow;
        private int sessionBars;
        private int sessionDir;
        private double sessionLevel;
        private bool sessionBreakoutSeen;
        private bool sessionTraded;

        private int onebeeCycleDir;
        private bool onebeeBoxActive;
        private double onebeeBoxHigh;
        private double onebeeBoxLow;

        private class ReportBucket
        {
            public int Trades;
            public double Net;
            public int Wins;
            public int Losses;

            public void Add(double pnl)
            {
                Trades++;
                Net += pnl;
                if (pnl > 0)
                    Wins++;
                else if (pnl < 0)
                    Losses++;
            }
        }

        #region Parameters
        [NinjaScriptProperty]
        [Display(Name = "Ret20 Min", GroupName = "Monthly Regime", Order = 1)]
        public double Ret20Min { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Ret240 Min", GroupName = "Monthly Regime", Order = 2)]
        public double Ret240Min { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ADR20 Min Points", GroupName = "Monthly Regime", Order = 3)]
        public double Adr20Min { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Daily Stop Points", GroupName = "Risk", Order = 1)]
        public double DailyStopPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Quantity", GroupName = "Risk", Order = 2)]
        public int Quantity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Grid", GroupName = "Components", Order = 1)]
        public bool EnableGrid { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Session", GroupName = "Components", Order = 2)]
        public bool EnableSession { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Onebee", GroupName = "Components", Order = 3)]
        public bool EnableOnebee { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid Start Hour KST", GroupName = "Grid", Order = 1)]
        public int GridStartHourKst { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid End Hour KST", GroupName = "Grid", Order = 2)]
        public int GridEndHourKst { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid Pending Bars", GroupName = "Grid", Order = 3)]
        public int GridPendingBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid Step Points", GroupName = "Grid", Order = 4)]
        public double GridStepPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid Stop Points", GroupName = "Grid", Order = 5)]
        public double GridStopPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid Trail Arm Points", GroupName = "Grid", Order = 6)]
        public double GridTrailArmPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid Trail Points", GroupName = "Grid", Order = 7)]
        public double GridTrailPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Grid Third Recovery Points", GroupName = "Grid", Order = 8)]
        public double GridThirdRecoveryPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Session Body Ratio Min", GroupName = "Session", Order = 1)]
        public double SessionBodyRatioMin { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Session Risk Reward", GroupName = "Session", Order = 2)]
        public double SessionRiskReward { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Onebee ATR Length", GroupName = "Onebee", Order = 1)]
        public int OnebeeAtrLength { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Onebee Target KTR", GroupName = "Onebee", Order = 2)]
        public double OnebeeTargetKtr { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Onebee Stop KTR", GroupName = "Onebee", Order = 3)]
        public double OnebeeStopKtr { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export Reports", GroupName = "Report", Order = 1)]
        public bool ExportReports { get; set; }
        #endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "Candidate1RefinedXauusd";
                Description = "Candidate 1 refined XAUUSD strategy: monthly regime, 5m grid, session retest, 2m Onebee, daily stop, yearly/monthly CSV report.";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 3;
                EntryHandling = EntryHandling.UniqueEntries;
                IsExitOnSessionCloseStrategy = false;
                IncludeCommission = true;
                IsInstantiatedOnEachOptimizationIteration = false;

                Ret20Min = 0.0084;
                Ret240Min = -0.0428;
                Adr20Min = 18.0;
                DailyStopPoints = 50.0;
                Quantity = 1;

                EnableGrid = true;
                EnableSession = true;
                EnableOnebee = true;

                GridStartHourKst = 9;
                GridEndHourKst = 18;
                GridPendingBars = 10;
                GridStepPoints = 10.0;
                GridStopPoints = 35.0;
                GridTrailArmPoints = 10.0;
                GridTrailPoints = 10.0;
                GridThirdRecoveryPoints = 3.0;

                SessionBodyRatioMin = 0.90;
                SessionRiskReward = 2.0;

                OnebeeAtrLength = 30;
                OnebeeTargetKtr = 2.0;
                OnebeeStopKtr = 5.5;

                ExportReports = true;
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 2);
                AddDataSeries(BarsPeriodType.Day, 1);
            }
            else if (State == State.DataLoaded)
            {
                kstZone = FindZone("Korea Standard Time");
                londonZone = FindZone("GMT Standard Time");
                newYorkZone = FindZone("Eastern Standard Time");
            }
            else if (State == State.Terminated)
            {
                UpdateClosedTradeReports();
                if (ExportReports)
                    ExportReportCsv();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == DailyBars)
            {
                UpdateMonthlyRegime();
                return;
            }

            if (CurrentBars[PrimaryBars] < 260 || CurrentBars[TwoMinuteBars] < 140 || CurrentBars[DailyBars] < 260)
                return;

            ResetDailyStateIfNeeded(BarsInProgress);
            UpdateClosedTradeReports();

            if (BarsInProgress == TwoMinuteBars)
            {
                RunOnebeeComponent();
                return;
            }

            if (BarsInProgress != PrimaryBars)
                return;

            RunGridComponent();
            RunSessionComponent();
        }

        private void UpdateMonthlyRegime()
        {
            if (CurrentBars[DailyBars] < 241)
                return;

            DateTime kst = ToKst(Times[DailyBars][0], DailyBars);
            int monthKey = kst.Year * 100 + kst.Month;

            double ret20 = Closes[DailyBars][1] / Closes[DailyBars][20] - 1.0;
            double ret240 = Closes[DailyBars][1] / Closes[DailyBars][240] - 1.0;
            double adr20 = 0.0;
            for (int i = 1; i <= 20; i++)
                adr20 += Highs[DailyBars][i] - Lows[DailyBars][i];
            adr20 /= 20.0;

            regimeByMonth[monthKey] = ret20 >= Ret20Min && ret240 >= Ret240Min && adr20 >= Adr20Min;
        }

        private void RunGridComponent()
        {
            if (!EnableGrid)
                return;

            bool flat = Position.MarketPosition == MarketPosition.Flat;
            DateTime kst = ToKst(Time[0], PrimaryBars);
            bool canOpen = CanOpenNewTrade(kst);

            double bb20Mid = Sma(PrimaryBars, "close", 20);
            double bb20Std = Std(PrimaryBars, "close", 20);
            double bb20Up = bb20Mid + 2.0 * bb20Std;
            double bb20Down = bb20Mid - 2.0 * bb20Std;
            double bb44OpenMid = Sma(PrimaryBars, "open", 4);
            double bb44OpenStd = Std(PrimaryBars, "open", 4);
            double bb44OpenUp = bb44OpenMid + 4.0 * bb44OpenStd;
            double bb44OpenDown = bb44OpenMid - 4.0 * bb44OpenStd;

            if (canOpen && flat && InKstHourRange(kst, GridStartHourKst, GridEndHourKst))
            {
                bool longBreak = Close[0] > bb20Up && Close[0] > bb44OpenUp;
                bool shortBreak = Close[0] < bb20Down && Close[0] < bb44OpenDown;
                if (longBreak)
                {
                    gridDir = 1;
                    gridBarsLeft = GridPendingBars;
                    gridEntry1 = bb44OpenDown;
                    gridStopPrice = gridEntry1 - GridStopPoints;
                    gridReduced = false;
                    gridTrailing = false;
                    gridTrailStop = 0;
                }
                else if (shortBreak)
                {
                    gridDir = -1;
                    gridBarsLeft = GridPendingBars;
                    gridEntry1 = bb44OpenUp;
                    gridStopPrice = gridEntry1 + GridStopPoints;
                    gridReduced = false;
                    gridTrailing = false;
                    gridTrailStop = 0;
                }
            }

            if (flat && canOpen && gridBarsLeft > 0 && gridDir != 0)
            {
                if (gridDir == 1)
                {
                    EnterLongLimit(PrimaryBars, false, Quantity, gridEntry1, "Grid1");
                    EnterLongLimit(PrimaryBars, false, Quantity, gridEntry1 - GridStepPoints, "Grid2");
                    EnterLongLimit(PrimaryBars, false, Quantity, gridEntry1 - 2.0 * GridStepPoints, "Grid3");
                }
                else
                {
                    EnterShortLimit(PrimaryBars, false, Quantity, gridEntry1, "Grid1");
                    EnterShortLimit(PrimaryBars, false, Quantity, gridEntry1 + GridStepPoints, "Grid2");
                    EnterShortLimit(PrimaryBars, false, Quantity, gridEntry1 + 2.0 * GridStepPoints, "Grid3");
                }
                gridBarsLeft--;
            }
            else if (flat && gridBarsLeft == 0)
            {
                gridDir = 0;
            }

            if (Position.MarketPosition == MarketPosition.Flat || gridDir == 0)
                return;

            bool isLong = Position.MarketPosition == MarketPosition.Long;
            double avg = Position.AveragePrice;
            int qty = Math.Abs(Position.Quantity);

            bool hardStopHit = isLong ? Low[0] <= gridStopPrice : High[0] >= gridStopPrice;
            if (hardStopHit)
            {
                if (isLong)
                    ExitLong("GridStop", "");
                else
                    ExitShort("GridStop", "");
                gridDir = 0;
                return;
            }

            if (qty >= 3 * Quantity && !gridReduced)
            {
                double recoveryPrice = isLong ? avg + GridThirdRecoveryPoints : avg - GridThirdRecoveryPoints;
                bool recoveryHit = isLong ? High[0] >= recoveryPrice : Low[0] <= recoveryPrice;
                if (recoveryHit)
                {
                    int reduceQty = Math.Max(1, qty / 2);
                    if (isLong)
                        ExitLong(reduceQty, "GridReduce", "");
                    else
                        ExitShort(reduceQty, "GridReduce", "");
                    gridReduced = true;
                    gridTrailing = true;
                    gridTrailStop = avg;
                }
            }

            bool armHit = isLong ? Close[0] >= avg + GridTrailArmPoints : Close[0] <= avg - GridTrailArmPoints;
            if (armHit || gridReduced)
            {
                gridTrailing = true;
                if (isLong)
                    gridTrailStop = gridTrailStop <= 0 ? Math.Max(avg, Close[0] - GridTrailPoints) : Math.Max(gridTrailStop, Math.Max(avg, Close[0] - GridTrailPoints));
                else
                    gridTrailStop = gridTrailStop <= 0 ? Math.Min(avg, Close[0] + GridTrailPoints) : Math.Min(gridTrailStop, Math.Min(avg, Close[0] + GridTrailPoints));
            }

            if (gridTrailing)
            {
                if (isLong)
                    ExitLongStopMarket(PrimaryBars, true, Math.Abs(Position.Quantity), gridTrailStop, "GridTrail", "");
                else
                    ExitShortStopMarket(PrimaryBars, true, Math.Abs(Position.Quantity), gridTrailStop, "GridTrail", "");
            }
        }

        private void RunSessionComponent()
        {
            if (!EnableSession)
                return;

            DateTime kst = ToKst(Time[0], PrimaryBars);
            bool reset = IsSessionReset(Time[0], PrimaryBars);
            if (reset)
            {
                sessionHigh = High[0];
                sessionLow = Low[0];
                sessionBars = 1;
                sessionDir = 0;
                sessionLevel = 0;
                sessionBreakoutSeen = false;
                sessionTraded = false;
            }
            else if (sessionBars > 0 && sessionBars < 3)
            {
                sessionHigh = Math.Max(sessionHigh, High[0]);
                sessionLow = Math.Min(sessionLow, Low[0]);
                sessionBars++;
            }

            if (sessionBars >= 3 && !sessionBreakoutSeen)
            {
                double bodyRatio = BodyRatio(PrimaryBars);
                if (Close[0] > sessionHigh && bodyRatio >= SessionBodyRatioMin)
                {
                    sessionDir = 1;
                    sessionLevel = sessionHigh;
                    sessionBreakoutSeen = true;
                }
                else if (Close[0] < sessionLow && bodyRatio >= SessionBodyRatioMin)
                {
                    sessionDir = -1;
                    sessionLevel = sessionLow;
                    sessionBreakoutSeen = true;
                }
            }

            if (!CanOpenNewTrade(kst) || sessionTraded || Position.MarketPosition != MarketPosition.Flat || !sessionBreakoutSeen)
                return;

            if (sessionDir == 1 && Low[0] <= sessionLevel)
            {
                double risk = Close[0] - sessionLow;
                if (risk > TickSize)
                {
                    SetStopLoss("SessionLong", CalculationMode.Price, sessionLow, false);
                    SetProfitTarget("SessionLong", CalculationMode.Price, Close[0] + SessionRiskReward * risk);
                    EnterLong(PrimaryBars, Quantity, "SessionLong");
                    sessionTraded = true;
                }
            }
            else if (sessionDir == -1 && High[0] >= sessionLevel)
            {
                double risk = sessionHigh - Close[0];
                if (risk > TickSize)
                {
                    SetStopLoss("SessionShort", CalculationMode.Price, sessionHigh, false);
                    SetProfitTarget("SessionShort", CalculationMode.Price, Close[0] - SessionRiskReward * risk);
                    EnterShort(PrimaryBars, Quantity, "SessionShort");
                    sessionTraded = true;
                }
            }
        }

        private void RunOnebeeComponent()
        {
            if (!EnableOnebee || Position.MarketPosition != MarketPosition.Flat)
                return;

            DateTime kst = ToKst(Times[TwoMinuteBars][0], TwoMinuteBars);
            if (!CanOpenNewTrade(kst))
                return;

            double sma20 = Sma(TwoMinuteBars, "close", 20);
            double sma120 = Sma(TwoMinuteBars, "close", 120);
            double sma20Prev = Sma(TwoMinuteBars, "close", 20, 1);
            double sma120Prev = Sma(TwoMinuteBars, "close", 120, 1);
            if (sma20Prev <= sma120Prev && sma20 > sma120)
            {
                onebeeCycleDir = 1;
                onebeeBoxActive = false;
            }
            else if (sma20Prev >= sma120Prev && sma20 < sma120)
            {
                onebeeCycleDir = -1;
                onebeeBoxActive = false;
            }

            double priorHigh = Highest(TwoMinuteBars, 60, 1);
            double priorLow = Lowest(TwoMinuteBars, 60, 1);
            double range = Highs[TwoMinuteBars][0] - Lows[TwoMinuteBars][0];
            double upperWickRatio = range > 0 ? (Highs[TwoMinuteBars][0] - Math.Max(Opens[TwoMinuteBars][0], Closes[TwoMinuteBars][0])) / range : 1.0;
            double lowerWickRatio = range > 0 ? (Math.Min(Opens[TwoMinuteBars][0], Closes[TwoMinuteBars][0]) - Lows[TwoMinuteBars][0]) / range : 1.0;

            if (!onebeeBoxActive)
            {
                if (onebeeCycleDir == 1 && Closes[TwoMinuteBars][0] > priorHigh && Closes[TwoMinuteBars][0] > Opens[TwoMinuteBars][0] && upperWickRatio <= 0.10)
                {
                    onebeeBoxActive = true;
                    onebeeBoxHigh = Highs[TwoMinuteBars][0];
                    onebeeBoxLow = Lows[TwoMinuteBars][0];
                }
                else if (onebeeCycleDir == -1 && Closes[TwoMinuteBars][0] < priorLow && Closes[TwoMinuteBars][0] < Opens[TwoMinuteBars][0] && lowerWickRatio <= 0.10)
                {
                    onebeeBoxActive = true;
                    onebeeBoxHigh = Highs[TwoMinuteBars][0];
                    onebeeBoxLow = Lows[TwoMinuteBars][0];
                }
            }

            if (!onebeeBoxActive)
                return;

            double bb44OpenMid = Sma(TwoMinuteBars, "open", 4);
            double bb44OpenStd = Std(TwoMinuteBars, "open", 4);
            double bb44OpenUp = bb44OpenMid + 4.0 * bb44OpenStd;
            double bb44OpenDown = bb44OpenMid - 4.0 * bb44OpenStd;
            bool bodyInside = Math.Min(Opens[TwoMinuteBars][0], Closes[TwoMinuteBars][0]) >= onebeeBoxLow
                && Math.Max(Opens[TwoMinuteBars][0], Closes[TwoMinuteBars][0]) <= onebeeBoxHigh;
            double ktrProxy = AtrProxy(TwoMinuteBars, OnebeeAtrLength);
            if (ktrProxy <= 0)
                return;

            if (onebeeCycleDir == 1 && Lows[TwoMinuteBars][0] <= bb44OpenDown && bodyInside && Closes[TwoMinuteBars][0] > Opens[TwoMinuteBars][0])
            {
                double entry = Closes[TwoMinuteBars][0];
                SetStopLoss("OnebeeLong", CalculationMode.Price, entry - OnebeeStopKtr * ktrProxy, false);
                SetProfitTarget("OnebeeLong", CalculationMode.Price, entry + OnebeeTargetKtr * ktrProxy);
                EnterLong(TwoMinuteBars, Quantity, "OnebeeLong");
                onebeeBoxActive = false;
            }
            else if (onebeeCycleDir == -1 && Highs[TwoMinuteBars][0] >= bb44OpenUp && bodyInside && Closes[TwoMinuteBars][0] < Opens[TwoMinuteBars][0])
            {
                double entry = Closes[TwoMinuteBars][0];
                SetStopLoss("OnebeeShort", CalculationMode.Price, entry + OnebeeStopKtr * ktrProxy, false);
                SetProfitTarget("OnebeeShort", CalculationMode.Price, entry - OnebeeTargetKtr * ktrProxy);
                EnterShort(TwoMinuteBars, Quantity, "OnebeeShort");
                onebeeBoxActive = false;
            }
        }

        private bool CanOpenNewTrade(DateTime kst)
        {
            int monthKey = kst.Year * 100 + kst.Month;
            bool regimeOk;
            if (!regimeByMonth.TryGetValue(monthKey, out regimeOk) || !regimeOk)
                return false;
            return dayPnl > -DailyStopPoints;
        }

        private void ResetDailyStateIfNeeded(int bip)
        {
            DateTime kst = ToKst(Times[bip][0], bip);
            int dayKey = kst.Year * 10000 + kst.Month * 100 + kst.Day;
            if (currentKstDayKey != dayKey)
            {
                currentKstDayKey = dayKey;
                dayPnl = 0.0;
            }
        }

        private void UpdateClosedTradeReports()
        {
            int count = SystemPerformance.AllTrades.Count;
            if (count <= lastTradeCount)
                return;

            for (int i = lastTradeCount; i < count; i++)
            {
                Trade trade = SystemPerformance.AllTrades[i];
                double pnl = trade.ProfitPoints;
                DateTime exitTime = trade.Exit.Time;
                DateTime kst = ToKst(exitTime, PrimaryBars);
                int yearKey = kst.Year;
                int monthKey = kst.Year * 100 + kst.Month;
                if (kst.Year * 10000 + kst.Month * 100 + kst.Day == currentKstDayKey)
                    dayPnl += pnl;
                AddReport(yearly, yearKey, pnl);
                AddReport(monthly, monthKey, pnl);
            }
            lastTradeCount = count;
        }

        private void ExportReportCsv()
        {
            string dir = Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "Candidate1RefinedReports");
            Directory.CreateDirectory(dir);
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            WriteReport(Path.Combine(dir, "candidate1_yearly_" + stamp + ".csv"), yearly, "year");
            WriteReport(Path.Combine(dir, "candidate1_monthly_" + stamp + ".csv"), monthly, "month");
            Print("Candidate1 reports exported: " + dir);
        }

        private void WriteReport(string path, Dictionary<int, ReportBucket> buckets, string firstColumnName)
        {
            using (StreamWriter writer = new StreamWriter(path, false))
            {
                writer.WriteLine(firstColumnName + ",trades,net,wins,losses,win_rate");
                List<int> keys = new List<int>(buckets.Keys);
                keys.Sort();
                foreach (int key in keys)
                {
                    ReportBucket bucket = buckets[key];
                    double winRate = bucket.Trades > 0 ? 100.0 * bucket.Wins / bucket.Trades : 0.0;
                    writer.WriteLine(string.Format(
                        System.Globalization.CultureInfo.InvariantCulture,
                        "{0},{1},{2:F2},{3},{4},{5:F2}",
                        key,
                        bucket.Trades,
                        bucket.Net,
                        bucket.Wins,
                        bucket.Losses,
                        winRate));
                }
            }
        }

        private void AddReport(Dictionary<int, ReportBucket> target, int key, double pnl)
        {
            ReportBucket bucket;
            if (!target.TryGetValue(key, out bucket))
            {
                bucket = new ReportBucket();
                target[key] = bucket;
            }
            bucket.Add(pnl);
        }

        private bool IsSessionReset(DateTime barTime, int bip)
        {
            DateTime kst = ToKst(barTime, bip);
            DateTime london = ConvertTime(barTime, bip, londonZone);
            DateTime ny = ConvertTime(barTime, bip, newYorkZone);
            bool asia = kst.Hour == 8 && kst.Minute == 30;
            bool europe = london.Hour == 8 && london.Minute == 0;
            bool newYork = ny.Hour == 9 && ny.Minute == 30;
            return asia || europe || newYork;
        }

        private bool InKstHourRange(DateTime kst, int startHour, int endHour)
        {
            if (startHour < endHour)
                return kst.Hour >= startHour && kst.Hour < endHour;
            return kst.Hour >= startHour || kst.Hour < endHour;
        }

        private double BodyRatio(int bip)
        {
            double range = Highs[bip][0] - Lows[bip][0];
            return range > 0 ? Math.Abs(Closes[bip][0] - Opens[bip][0]) / range : 0.0;
        }

        private double Sma(int bip, string field, int length)
        {
            return Sma(bip, field, length, 0);
        }

        private double Sma(int bip, string field, int length, int offset)
        {
            if (CurrentBars[bip] < length + offset)
                return 0.0;
            double sum = 0.0;
            for (int i = offset; i < offset + length; i++)
                sum += ValueAt(bip, field, i);
            return sum / length;
        }

        private double Std(int bip, string field, int length)
        {
            if (CurrentBars[bip] < length)
                return 0.0;
            double mean = Sma(bip, field, length);
            double sumSq = 0.0;
            for (int i = 0; i < length; i++)
            {
                double d = ValueAt(bip, field, i) - mean;
                sumSq += d * d;
            }
            return Math.Sqrt(sumSq / length);
        }

        private double Highest(int bip, int length, int offset)
        {
            double v = double.MinValue;
            for (int i = offset; i < offset + length; i++)
                v = Math.Max(v, Highs[bip][i]);
            return v;
        }

        private double Lowest(int bip, int length, int offset)
        {
            double v = double.MaxValue;
            for (int i = offset; i < offset + length; i++)
                v = Math.Min(v, Lows[bip][i]);
            return v;
        }

        private double AtrProxy(int bip, int length)
        {
            if (CurrentBars[bip] < length)
                return 0.0;
            double sum = 0.0;
            for (int i = 0; i < length; i++)
                sum += Highs[bip][i] - Lows[bip][i];
            return sum / length;
        }

        private double ValueAt(int bip, string field, int barsAgo)
        {
            if (field == "open")
                return Opens[bip][barsAgo];
            if (field == "high")
                return Highs[bip][barsAgo];
            if (field == "low")
                return Lows[bip][barsAgo];
            return Closes[bip][barsAgo];
        }

        private DateTime ToKst(DateTime time, int bip)
        {
            return ConvertTime(time, bip, kstZone);
        }

        private DateTime ConvertTime(DateTime time, int bip, TimeZoneInfo target)
        {
            try
            {
                TimeZoneInfo source = BarsArray[bip].TradingHours.TimeZoneInfo;
                return TimeZoneInfo.ConvertTime(time, source, target);
            }
            catch
            {
                return time;
            }
        }

        private TimeZoneInfo FindZone(string id)
        {
            try
            {
                return TimeZoneInfo.FindSystemTimeZoneById(id);
            }
            catch
            {
                return TimeZoneInfo.Local;
            }
        }
    }
}

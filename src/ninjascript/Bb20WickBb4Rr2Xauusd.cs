#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

// NinjaTrader 8 port of the fixed 1:2 BB20 wick -> opposite BB4 pullback rule.
// Primary series: XAUUSD / Gold CFD, 2 minute.
// The Python research reference is src/scripts/105_2m_bb20_wick_bb4_rr2.py.
// Commission and slippage must be configured in the NinjaTrader Analyzer.

namespace NinjaTrader.NinjaScript.Strategies
{
    public class Bb20WickBb4Rr2Xauusd : Strategy
    {
        private const int Primary = 0;
        private readonly Dictionary<string, PendingSignal> pending = new Dictionary<string, PendingSignal>();
        private readonly Dictionary<int, ReportBucket> yearly = new Dictionary<int, ReportBucket>();
        private readonly Dictionary<int, ReportBucket> monthly = new Dictionary<int, ReportBucket>();
        private TimeZoneInfo kstZone;
        private int signalNumber;
        private int lastReportedTradeCount;

        private class PendingSignal
        {
            public string Name;
            public int Direction;
            public int BreakoutBar;
            public int ExpiryBar;
            public double LimitPrice;
            public double BreakoutHigh;
            public double BreakoutLow;
            public Order Order;
            public int FillBar = -1;
            public bool TimeExitSubmitted;
        }

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
                if (pnl > 0) Wins++;
                else if (pnl < 0) Losses++;
            }
        }

        #region Parameters
        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Pending Bars", GroupName = "Entry", Order = 1)]
        public int PendingBars { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 10.0)]
        [Display(Name = "Stop Buffer Points", GroupName = "Risk", Order = 1)]
        public double StopBufferPoints { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 20.0)]
        [Display(Name = "Minimum Risk Points", GroupName = "Risk", Order = 2)]
        public double MinimumRiskPoints { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "Maximum Risk Points", GroupName = "Risk", Order = 3)]
        public double MaximumRiskPoints { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Maximum Hold Bars", GroupName = "Exit", Order = 1)]
        public int MaximumHoldBars { get; set; }

        [NinjaScriptProperty]
        [Range(1, 5)]
        [Display(Name = "Maximum Concurrent Entries", GroupName = "Risk", Order = 4)]
        public int MaximumConcurrentEntries { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Use Prior Month Gate", GroupName = "Regime", Order = 1)]
        public bool UsePriorMonthGate { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Prior Month Close Minimum", GroupName = "Regime", Order = 2)]
        public double PriorMonthCloseMinimum { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export Reports", GroupName = "Report", Order = 1)]
        public bool ExportReports { get; set; }
        #endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "Bb20WickBb4Rr2Xauusd";
                Description = "2m BB20 wick to opposite BB4 pullback, fixed 1:2 RR.";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 5;
                EntryHandling = EntryHandling.UniqueEntries;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                IsExitOnSessionCloseStrategy = false;
                IncludeCommission = true;
                IsInstantiatedOnEachOptimizationIteration = false;

                PendingBars = 30;
                StopBufferPoints = 0.5;
                MinimumRiskPoints = 0.8;
                MaximumRiskPoints = 4.0;
                MaximumHoldBars = 20;
                MaximumConcurrentEntries = 5;
                UsePriorMonthGate = true;
                PriorMonthCloseMinimum = 3772.782;
                ExportReports = true;
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Day, 1);
                EntriesPerDirection = MaximumConcurrentEntries;
            }
            else if (State == State.DataLoaded)
            {
                kstZone = FindZone("Korea Standard Time");
            }
            else if (State == State.Terminated)
            {
                UpdateTradeReports();
                if (ExportReports)
                    ExportReportCsv();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != Primary)
                return;
            if (CurrentBars[Primary] < 120 || CurrentBars[1] < 260)
                return;

            UpdateTradeReports();
            CancelExpiredSignals();

            DateTime kst = ToKst(Time[0]);
            if (IsRegimeAllowed(kst))
                SubmitNewSignal();
            MaintainPendingOrders(IsEntryTime(kst));
            UpdateTimeExits();
        }

        private void SubmitNewSignal()
        {
            double bb20Mean = Mean(20, false, 0);
            double bb20Std = StdDev(20, false, 0, bb20Mean);
            double bb4Mean = Mean(4, true, 0);
            double bb4Std = StdDev(4, true, 0, bb4Mean);
            if (bb20Std <= 0 || bb4Std <= 0)
                return;

            bool longSignal = High[0] > bb20Mean + 2.0 * bb20Std;
            bool shortSignal = Low[0] < bb20Mean - 2.0 * bb20Std;
            if (longSignal == shortSignal)
                return;

            int direction = longSignal ? 1 : -1;
            double limitPrice = longSignal ? bb4Mean - 4.0 * bb4Std : bb4Mean + 4.0 * bb4Std;
            if (double.IsNaN(limitPrice) || double.IsInfinity(limitPrice))
                return;

            string name = (direction > 0 ? "L" : "S") + signalNumber++;
            PendingSignal signal = new PendingSignal
            {
                Name = name,
                Direction = direction,
                BreakoutBar = CurrentBar,
                ExpiryBar = CurrentBar + PendingBars,
                LimitPrice = limitPrice,
                BreakoutHigh = High[0],
                BreakoutLow = Low[0]
            };
            pending[name] = signal;

        }

        private void CancelExpiredSignals()
        {
            List<string> remove = new List<string>();
            foreach (KeyValuePair<string, PendingSignal> item in pending)
            {
                PendingSignal signal = item.Value;
                if (signal.Order != null && signal.Order.OrderState == OrderState.Filled)
                    continue;
                if (CurrentBar > signal.ExpiryBar)
                {
                    if (signal.Order != null)
                        CancelOrder(signal.Order);
                    remove.Add(item.Key);
                }
            }
            foreach (string key in remove)
                pending.Remove(key);
        }

        private void MaintainPendingOrders(bool entryWindow)
        {
            foreach (KeyValuePair<string, PendingSignal> item in pending)
            {
                PendingSignal signal = item.Value;
                if (signal.Order != null && signal.Order.OrderState == OrderState.Filled)
                    continue;

                if (!entryWindow)
                {
                    if (signal.Order != null && (signal.Order.OrderState == OrderState.Working || signal.Order.OrderState == OrderState.Accepted))
                    {
                        CancelOrder(signal.Order);
                        signal.Order = null;
                    }
                    continue;
                }

                if (signal.Order == null || signal.Order.OrderState == OrderState.Cancelled || signal.Order.OrderState == OrderState.Rejected)
                {
                    if (signal.Direction > 0)
                        EnterLongLimit(Primary, true, DefaultQuantity, signal.LimitPrice, signal.Name);
                    else
                        EnterShortLimit(Primary, true, DefaultQuantity, signal.LimitPrice, signal.Name);
                }
            }
        }

        protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity, int filled,
            double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error, string comment)
        {
            PendingSignal signal;
            if (order != null && pending.TryGetValue(order.Name, out signal))
                signal.Order = order;
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity,
            MarketPosition marketPosition, string orderId, DateTime time)
        {
            if (execution == null || execution.Order == null)
                return;

            PendingSignal signal;
            if (!pending.TryGetValue(execution.Order.Name, out signal))
                return;
            if (execution.Order.OrderAction != OrderAction.Buy && execution.Order.OrderAction != OrderAction.SellShort)
                return;

            int fillBar = CurrentBar;
            double low = Low[0];
            double high = High[0];
            for (int i = signal.BreakoutBar; i <= fillBar && i >= 0; i++)
            {
                int ago = CurrentBar - i;
                if (ago < 0 || ago > CurrentBar)
                    continue;
                low = Math.Min(low, Low[ago]);
                high = Math.Max(high, High[ago]);
            }

            double stop = signal.Direction > 0 ? low - StopBufferPoints : high + StopBufferPoints;
            double risk = signal.Direction > 0 ? price - stop : stop - price;
            signal.FillBar = fillBar;
            if (risk < MinimumRiskPoints || risk > MaximumRiskPoints)
            {
                if (signal.Direction > 0)
                    ExitLong("RiskReject_" + signal.Name, signal.Name);
                else
                    ExitShort("RiskReject_" + signal.Name, signal.Name);
                return;
            }

            double target = signal.Direction > 0 ? price + 2.0 * risk : price - 2.0 * risk;
            if (signal.Direction > 0)
            {
                ExitLongStopMarket(Primary, true, quantity, stop, "Stop_" + signal.Name, signal.Name);
                ExitLongLimit(Primary, true, quantity, target, "Target_" + signal.Name, signal.Name);
            }
            else
            {
                ExitShortStopMarket(Primary, true, quantity, stop, "Stop_" + signal.Name, signal.Name);
                ExitShortLimit(Primary, true, quantity, target, "Target_" + signal.Name, signal.Name);
            }
        }

        private void UpdateTimeExits()
        {
            foreach (KeyValuePair<string, PendingSignal> item in pending)
            {
                PendingSignal signal = item.Value;
                if (signal.Order == null || signal.Order.OrderState != OrderState.Filled)
                    continue;
                if (signal.TimeExitSubmitted || signal.FillBar < 0 || CurrentBar - signal.FillBar < MaximumHoldBars)
                    continue;
                if (signal.Direction > 0)
                    ExitLong("Time_" + signal.Name, signal.Name);
                else
                    ExitShort("Time_" + signal.Name, signal.Name);
                signal.TimeExitSubmitted = true;
            }
        }

        private bool IsEntryTime(DateTime kst)
        {
            int minute = kst.Hour * 60 + kst.Minute;
            return minute >= 9 * 60 && minute < 18 * 60;
        }

        private bool IsRegimeAllowed(DateTime kst)
        {
            if (!UsePriorMonthGate)
                return true;
            DateTime currentMonth = new DateTime(kst.Year, kst.Month, 1);
            for (int i = 1; i <= CurrentBars[1]; i++)
            {
                DateTime dailyKst = ToKst(Times[1][i]);
                if (dailyKst < currentMonth)
                    return Closes[1][i] >= PriorMonthCloseMinimum;
            }
            return false;
        }

        private double Mean(int length, bool useOpen, int offset)
        {
            double sum = 0.0;
            for (int i = offset; i < offset + length; i++)
                sum += useOpen ? Opens[Primary][i] : Closes[Primary][i];
            return sum / length;
        }

        private double StdDev(int length, bool useOpen, int offset, double mean)
        {
            double sum = 0.0;
            for (int i = offset; i < offset + length; i++)
            {
                double value = useOpen ? Opens[Primary][i] : Closes[Primary][i];
                double diff = value - mean;
                sum += diff * diff;
            }
            return Math.Sqrt(sum / length);
        }

        private void UpdateTradeReports()
        {
            int count = SystemPerformance.AllTrades.Count;
            if (count <= lastReportedTradeCount)
                return;
            for (int i = lastReportedTradeCount; i < count; i++)
            {
                Trade trade = SystemPerformance.AllTrades[i];
                DateTime kst = ToKst(trade.Exit.Time);
                AddReport(yearly, kst.Year, trade.ProfitPoints);
                AddReport(monthly, kst.Year * 100 + kst.Month, trade.ProfitPoints);
            }
            lastReportedTradeCount = count;
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

        private void ExportReportCsv()
        {
            string directory = Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "Bb20WickBb4Rr2Reports");
            Directory.CreateDirectory(directory);
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture);
            WriteReport(Path.Combine(directory, "bb20_wick_rr2_yearly_" + stamp + ".csv"), yearly, "year");
            WriteReport(Path.Combine(directory, "bb20_wick_rr2_monthly_" + stamp + ".csv"), monthly, "month");
            Print("BB20 Wick RR2 reports exported: " + directory);
        }

        private void WriteReport(string path, Dictionary<int, ReportBucket> source, string keyName)
        {
            using (StreamWriter writer = new StreamWriter(path, false))
            {
                writer.WriteLine(keyName + ",trades,net_points,wins,losses,win_rate");
                List<int> keys = new List<int>(source.Keys);
                keys.Sort();
                foreach (int key in keys)
                {
                    ReportBucket bucket = source[key];
                    double winRate = bucket.Trades == 0 ? 0.0 : 100.0 * bucket.Wins / bucket.Trades;
                    writer.WriteLine(string.Format(CultureInfo.InvariantCulture, "{0},{1},{2:F4},{3},{4},{5:F2}", key, bucket.Trades, bucket.Net, bucket.Wins, bucket.Losses, winRate));
                }
            }
        }

        private DateTime ToKst(DateTime time)
        {
            try
            {
                return TimeZoneInfo.ConvertTime(time, BarsArray[Primary].TradingHours.TimeZoneInfo, kstZone);
            }
            catch
            {
                return time;
            }
        }

        private TimeZoneInfo FindZone(string id)
        {
            try { return TimeZoneInfo.FindSystemTimeZoneById(id); }
            catch { return TimeZoneInfo.Local; }
        }
    }
}

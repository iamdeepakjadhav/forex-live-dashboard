# 📥 Missing Data Filler System

Complete system to detect and fill missing hours in forex historical data.

## 📋 Overview

Your forex database has **gaps** in data - some hours are missing from the historical candles. This system automatically:

1. **Detects** which hours are missing (gap analysis)
2. **Downloads** missing data from Dukascopy
3. **Parses** tick data efficiently (parallel processing)
4. **Generates** candles for all timeframes (1m, 5m, 10m, 15m, 30m, 1H, 1D, etc.)
5. **Validates** that data was inserted correctly

## 🎯 Quick Start

### Step 1: Analyze Data Gaps

```bash
python fill_missing_data.py --report
```

This shows:
- How many hours are missing per symbol
- Data coverage % for each symbol
- Total gap statistics

**Example Output:**
```
Symbol          Missing Hours   Coverage
EURUSD.x        1,250 hours     98.5%
GBPUSD.x        892 hours       99.1%
AUDUSD.x        1,456 hours     97.8%
...
TOTAL           15,380 hours    98.2%
```

### Step 2: Fill All Gaps

```bash
python fill_missing_data.py --fill
```

This will:
- Download all missing hours from Dukascopy
- Parse ticks in parallel (fast!)
- Generate candles for all timeframes
- Insert into database
- Show progress in real-time

**Expected Time:** 10-30 minutes depending on total gap size

### Step 3: Validate Results

```bash
python fill_missing_data.py --fill --validate
```

Fills gaps AND verifies completion in one command.

### Step 4: View Detailed Report

```bash
python data_validation_report.py
```

Shows comprehensive database statistics:
- Total candles per timeframe
- Candles per symbol
- Date range coverage
- Coverage % by symbol

## 🛠️ Advanced Options

### Fill Specific Symbol Only

```bash
python fill_missing_data.py --symbol EURUSD --fill
```

Fills gaps for EURUSD.x only (faster for testing)

### Validate Without Filling

```bash
python data_validation_report.py
```

Shows current state without making changes.

### Adjust Parallel Workers

```bash
python fill_missing_data.py --fill --max-workers 8
```

Limit concurrent downloads (default: CPU count)

## 📊 How It Works

### Architecture

```
fill_missing_data.py (Orchestrator)
├── DataGapDetector (src/data_gap_detector.py)
│   ├── Queries database for existing hours
│   ├── Generates expected hours (excludes weekends)
│   └── Calculates gaps = expected - existing
│
├── DataFiller (src/data_filler.py)
│   ├── AsyncDukascopyDownloader (downloads ticks)
│   ├── DukascopyParser (parses binary data - multiprocessing)
│   ├── CandleGenerator (creates OHLCV candles)
│   └── DBStorage (inserts to database)
│
└── DataValidationReport (data_validation_report.py)
    └── Shows detailed statistics
```

### Gap Detection Logic

- Finds date range for each symbol (first hour to last hour in DB)
- Generates expected hours for that range
  - Includes all weekday hours (Monday-Friday 00:00-23:59 UTC)
  - Includes Friday up to 22:00 UTC (forex closes)
  - Includes Sunday from 22:00 UTC onwards (market reopens)
  - Skips all other weekend hours (forex closed)
- Compares with actual hours in database
- Missing hours = Expected - Actual

### Download & Fill Process

For each missing hour:
1. **Download** tick data from Dukascopy API
2. **Parse** binary tick data (1000s of ticks per hour)
3. **Generate** candles:
   - 1m candles (60 per hour)
   - 5m candles (12 per hour)
   - 10m, 15m, 30m, 1H, 1D, etc.
4. **Insert** with `ON CONFLICT DO NOTHING` (won't overwrite existing)
5. **Progress** shows real-time status

All steps use multiprocessing/async for maximum speed.

## ⚡ Performance

### Expected Speed

- **Detection:** ~1 minute for all symbols
- **Download:** ~100-200 hours/minute (depends on bandwidth)
- **Parsing:** ~500-1000 hours/minute (parallel)
- **Database Insert:** ~10,000 candles/second

### Example: Filling 10,000 missing hours
- Detection: 1 min
- Download: 50-100 min
- Parse: 10-20 min
- Insert: 1-2 min
- **Total: ~1.5-2.5 hours**

## 📁 Files Created

| File | Purpose |
|------|---------|
| `fill_missing_data.py` | Main orchestrator script |
| `src/data_gap_detector.py` | Detects missing hours (reusable class) |
| `src/data_filler.py` | Downloads, parses, generates candles (reusable) |
| `data_validation_report.py` | Detailed database statistics |
| `test_fill_script.py` | Quick test/verification script |

## 🔍 Troubleshooting

### "Connection failed"
```bash
# Check PostgreSQL is running
psql -U postgres -c "SELECT 1"
```

### Script too slow
```bash
# Reduce workers to prevent network saturation
python fill_missing_data.py --fill --max-workers 4
```

### "No data downloaded"
- Check internet connection
- Dukascopy might be rate limiting (wait 5 min, try again)
- Some old dates might not exist in Dukascopy (pre-2003 data unavailable)

### Partial fill
- Script can be re-run anytime - safe to interrupt and resume
- Uses `ON CONFLICT DO NOTHING` so won't create duplicates
- Progress from previous run is preserved

## 💡 Key Features

✅ **Non-destructive** - Won't overwrite existing data
✅ **Resumable** - Can interrupt and restart anytime
✅ **Fast** - Parallel download + parse + insert
✅ **Safe** - Validates week days/hours (no bogus weekend data)
✅ **Detailed Reports** - Knows exactly what's missing
✅ **Progressive** - Shows real-time progress
✅ **Reusable** - Can embed DataGapDetector/DataFiller in other scripts

## 📝 Common Workflows

### Complete Data Audit & Fill

```bash
# Step 1: See what's missing
python fill_missing_data.py --report

# Step 2: Fill everything
python fill_missing_data.py --fill

# Step 3: Verify completion
python data_validation_report.py
```

### Fill Specific Symbol

```bash
python fill_missing_data.py --symbol EURUSD --fill --validate
```

### Check After Some Time Passes

```bash
# New data arrives daily, detect new gaps
python data_validation_report.py

# If gaps exist:
python fill_missing_data.py --fill
```

## 📞 Support

If issues occur:
1. Check `fill_missing_data.py --report` output
2. Verify database connection: `psql test`
3. Try smaller --max-workers value
4. Check logs for specific error messages

---

**Status:** Production-ready
**Last Updated:** 2026-04-03
**Version:** 1.0

# 📊 COMPLETE FOREX SYSTEM CODEBASE ANALYSIS

## 🏗️ SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                    FOREX TRADING SYSTEM                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐                ┌─────────────────┐   │
│  │  DATA SOURCES    │                │   FLASK API     │   │
│  ├──────────────────┤                ├─────────────────┤   │
│  │                  │                │                 │   │
│  │ 1. Dukascopy API │──→ Parser ───→│  /api/data      │   │
│  │    (Historical   │                │ /api/symbols    │   │
│  │     OHLC)        │                │ /api/timeframes │   │
│  │                  │                │                 │   │
│  │ 2. MT5 Terminal  │──→ Collector ─→│ /api/tick       │   │
│  │    (Live Ticks)  │                │ /api/ticks      │   │
│  │                  │                │ /api/ticks/     │   │
│  └──────────────────┘                │   history       │   │
│           │                          │                 │   │
│           │                          └────────┬────────┘   │
│           │                                   │             │
│           └──────────────→ PostgreSQL Database │             │
│                               ↑                             │
│                          ┌────┴────┐                        │
│                          │ Tables: │                        │
│                          │ • candles_data                    │
│                          │ • ticks                           │
│                          │ • candles  (legacy)               │
│                          └─────────┘                        │
│                                   ↓                         │
│                          ┌──────────────────┐               │
│                          │  Frontend (HTML) │               │
│                          ├──────────────────┤               │
│                          │                  │               │
│                          │ • index.html     │               │
│                          │   (Main Chart)   │               │
│                          │                  │               │
│                          │ • ticks.html     │               │
│                          │   (History Ticks)│               │
│                          │                  │               │
│                          └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 FILE STRUCTURE

```
forex_system/
│
├── main.py                          # 🎯 Entry point for historical data download
├── test_apis.py                     # 🧪 Test API endpoints
├── cmd.txt                          # 🔧 Command shortcuts
├── database_schema.sql              # 📊 Database table definitions
│
├── src/                             # 📚 Core modules
│   ├── async_downloader.py          # ⚡ Async HTTP downloader (Dukascopy)
│   ├── downloader.py                # 🌐 Sync downloader (slower version)
│   ├── parser.py                    # 🔍 Binary .bi5 file parser
│   ├── candle_generator.py          # 📈 OHLC aggregator (1m, 5m, H1, D1, etc)
│   ├── db_storage.py                # 💾 PostgreSQL operations
│   ├── live_collector.py            # 🔴 MT5 real-time tick collector
│   └── __pycache__/
│
├── dashboard/                       # 🎨 Web interface
│   ├── app.py                       # 🚀 Flask REST API server
│   │
│   ├── templates/
│   │   ├── index.html               # 📊 Main dashboard (chart view)
│   │   └── ticks.html               # 📋 Tick history explorer
│   │
│   ├── static/
│   │   ├── lightweight-charts.js    # 📉 Charting library
│   │   ├── script.js                # 🎮 Main dashboard interactivity
│   │   ├── style.css                # 🎨 Styling
│   │   ├── ticks.js                 # 📜 Old ticks script (DEPRECATED)
│   │   └── ticks.html               # Copy of templates version
│   │
│   └── __pycache__/
│
└── data/                            # 📥 Downloaded files storage

```

---

## 🔌 DATA FLOW DIAGRAM

### **1️⃣ Historical Data Pipeline (GBPJPY only)**
```
Dukascopy
    ↓
main.py (GBPJPY symbol, date range)
    ↓
AsyncDukascopyDownloader
    ↓ (Downloads hourly .bi5 files)
    ↓
DukascopyParser (Parse binary → DataFrame)
    ↓
CandleGenerator (Resample: 1m, 5m, 15m, 30m, H1, H4, D1)
    ↓
DBStorage.insert_candles_batch()
    ↓
PostgreSQL: candles_data table
    ↓
Flask /api/data endpoint
    ↓
index.html (Display on chart)
```

### **2️⃣ Live Data Pipeline (EURUSD, GBPUSD, NZDUSD)**
```
MT5 Terminal
    ↓
MT5LiveCollector._init_mt5()
    ↓ (Connects to MT5 platform)
    ↓
Tick Thread: _tick_loop()
    ↓ (Every 200ms)
    ↓
mt5.symbol_info_tick() → get current bid/ask
    ↓
_save_tick() → INSERT into ticks table
    ↓
PostgreSQL: ticks table
    ↓
Two endpoints:
    → /api/tick (Live current tick)
    → /api/ticks (Latest tick per symbol)
    → /api/ticks/history (Filtered historical ticks)
    ↓
ticks.html (Display in table)
```

### **3️⃣ Candle Thread (Live Updates)**
```
MT5Raw Data (1m, 5m, H1, H4, D1 bars)
    ↓
_live_loop() (Every 30 seconds)
    ↓
mt5.copy_rates_range()
    ↓
_save_candles()
    ↓
PostgreSQL: candles_data table (UPSERT on conflict)
    ↓
/api/data endpoint
    ↓
Chart auto-updates
```

---

## 🗄️ DATABASE SCHEMA

### **candles_data Table** (Main - Partitioned by timeframe)
```sql
CREATE TABLE candles_data (
    symbol VARCHAR(10),              -- EURUSD.x, GBPJPY, etc
    timeframe VARCHAR(10),           -- 1m, 5m, H1, D1, etc
    datetime TIMESTAMP,              -- OHLC timestamp
    time_epoch BIGINT,               -- Unix timestamp (for fast queries)
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    PRIMARY KEY (symbol, timeframe, datetime)
)
PARTITION BY LIST (timeframe);

-- Partitions: candles_data_1m, _5m, _15m, _30m, _1H, _4H, _1D, etc
```

### **ticks Table** (Live tick data)
```sql
CREATE TABLE ticks (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10),              -- EURUSD.x, GBPUSD.x, NZDUSD.x
    tick_time TIMESTAMP,             -- When tick occurred
    bid DOUBLE PRECISION,            -- Bid price
    ask DOUBLE PRECISION,            -- Ask price
    mid DOUBLE PRECISION,            -- Mid price (bid+ask)/2
    spread DOUBLE PRECISION          -- Spread (ask-bid)
);

-- Index: idx_ticks_symbol_time (symbol, tick_time DESC)
```

### **candles Table** (Legacy - being replaced by candles_data)
```sql
CREATE TABLE candles (
    symbol VARCHAR(10),
    timeframe VARCHAR(10),
    datetime TIMESTAMP,
    open, high, low, close, volume DOUBLE PRECISION,
    PRIMARY KEY (symbol, timeframe, datetime)
);
```

---

## 🚀 FLASK API ENDPOINTS

| Endpoint | Method | Purpose | Returns |
|----------|--------|---------|---------|
| `/` | GET | Main dashboard | index.html |
| `/ticks` | GET | Tick history page | ticks.html |
| `/api/symbols` | GET | Available symbols | `["EURUSD.x", "GBPUSD.x", ...]` |
| `/api/timeframes` | GET | Available timeframes | `["1m", "5m", "1H", "1D", ...]` |
| `/api/data` | GET | Historical OHLC | `[{time, open, high, low, close, volume}]` |
| `/api/tick` | GET | Live current tick | `{symbol, time, bid, ask, last}` |
| `/api/ticks` | GET | Latest tick per symbol | `[{symbol, bid, ask, spread}]` |
| `/api/ticks/history` | GET | Filtered historical ticks | `[{time, symbol, bid, ask, spread}]` |

### **Query Parameters**

#### `/api/data`
```
?symbol=EURUSD.x
&timeframe=1H
&limit=10000
```

#### `/api/ticks/history`
```
?symbol=EURUSD.x           (optional, default: all)
&start_date=2024-01-15     (format: YYYY-MM-DD)
&end_date=2024-01-18       (format: YYYY-MM-DD)
&limit=1000                (default: 1000, max advised: 5000)
```

---

## 🔧 KEY MODULES EXPLAINED

### **1. main.py** - Historical Data Downloader
**Purpose:** Download historical OHLC data from Dukascopy
**Currently:** Only GBPJPY symbol configured
**Flow:**
1. Define date range
2. Download 1-hour binary files from Dukascopy
3. Parse binary data
4. Aggregate into multiple timeframes (1m, 5m, 1H, D1)
5. Store in `candles_data` table

**Config:**
```python
SYMBOLS = ["GBPJPY"]  # Only this for now
MAX_WORKERS = cpu_count()  # Parallel processing
```

---

### **2. src/live_collector.py** - MT5 Real-Time Collector
**Purpose:** Connect to MetaTrader5 and collect live ticks
**Currently Active For:** EURUSD.x, GBPUSD.x, NZDUSD.x
**Features:**
- **Tick Collection:** Every 200ms → saves bid/ask to DB
- **Candle Generation:** Every 30s → fetches and updates OHLC
- **Connection Pooling:** 5 DB connections max
- **Threading:** Separate threads for ticks + candles per symbol

**Init:**
```python
symbols = ["EURUSD.x", "GBPUSD.x", "NZDUSD.x"]
mt5_collector = MT5LiveCollector(DB_CONFIG, symbols)
mt5_collector.start_collection(
    timeframes=['1m','5m','15m','30m','1H','4H','1D'],
    interval=30  # seconds
)
```

---

### **3. src/db_storage.py** - Database Operations
**Key Methods:**
- `insert_candles_batch()` - Batch insert OHLC data
- `get_latest_timestamp()` - Get last candle datetime
- `get_existing_hours()` - Check what data we have

**Uses:** PostgreSQL with psycopg2

---

### **4. src/parser.py** - Binary Parser
**Input:** .bi5 compressed tick files from Dukascopy
**Output:** pandas DataFrame with datetime, bid, ask, volumes
**Format:** LZMA compressed binary
**Data Type:**
```
- ms: milliseconds (4 bytes)
- ask: price (4 bytes)  
- bid: price (4 bytes)
- ask_vol: volume (float)
- bid_vol: volume (float)
```

---

### **5. src/candle_generator.py** - OHLC Aggregator
**Input:** DataFrame with bid/ask ticks
**Output:** Multiple OHLC DataFrames
**Timeframes:** 1m, 5m, 10m, 15m, 30m, H1, D1 (configurable)
**Logic:**
1. Calculate mid price: `(bid + ask) / 2`
2. Sum volumes: `bid_vol + ask_vol`
3. Resample using pandas: `.resample().ohlc()`

---

### **6. dashboard/app.py** - Flask REST API
**Purpose:** Serve frontend + provide data endpoints
**Port:** 5000
**Features:**
- Global MT5 collector instance in background thread
- DB connection handling
- All API endpoints mentioned above

**Key Functions:**
```python
def get_db()                    # Get PostgreSQL connection
def init_mt5_collector()        # Start MT5 collector background thread
def get_tick_history()          # Filter ticks with date range
```

---

### **7. Frontend (HTML/JS)**

#### **index.html** - Main Dashboard
- Interactive chart (lightweight-charts library)
- Symbol selector dropdown
- Timeframe buttons (1m, 5m, 1H, D1)
- Live price display
- Auto-refreshing candles

#### **ticks.html** - Tick History
- Date range picker (start_date, end_date)
- Symbol selector (All, EURUSD, GBPUSD, NZDUSD)
- Row limit selector (100-5000)
- Table display: Date, Time, Symbol, Bid, Ask, Spread
- Auto-loads 1000 recent ticks on page open

---

## ⚙️ CONFIGURATION

### **DB Config** (dashboard/app.py)
```python
DB_CONFIG = {
    "host": "localhost",
    "user": "postgres",
    "password": "root",
    "database": "forex_data"
}
```

### **Symbols** (dashboard/app.py)
```python
# Live collection
symbols = ["EURUSD.x", "GBPUSD.x", "NZDUSD.x"]

# Historical (main.py)
SYMBOLS = ["GBPJPY"]  # Only this configured
```

### **Timeframes** (src/live_collector.py)
```python
TF_MAP = {
    '1m': mt5.TIMEFRAME_M1,
    '5m': mt5.TIMEFRAME_M5,
    '15m': mt5.TIMEFRAME_M15,
    '30m': mt5.TIMEFRAME_M30,
    '1H': mt5.TIMEFRAME_H1,
    '4H': mt5.TIMEFRAME_H4,
    '1D': mt5.TIMEFRAME_D1,
    '1W': mt5.TIMEFRAME_W1,
}
```

---

## 🚀 HOW TO RUN

### **1. Start Database**
```bash
# PostgreSQL should be running
psql -U postgres -d forex_data -f database_schema.sql
```

### **2. Start Flask API**
```bash
cd dashboard
python app.py
# Server runs on http://localhost:5000
```

### **3. (Optional) Download Historical Data**
```bash
cd ..
python main.py
# Will download GBPJPY from specified date range
```

### **4. Access Dashboard**
```
http://localhost:5000/              # Main chart
http://localhost:5000/ticks         # Tick history
```

---

## 🔍 DEBUGGING CHECKS

### **1. Is MT5 Connected?**
```bash
curl http://localhost:5000/api/status
# Response: {"status": "running", "connected": true, "symbols": [...]}
```

### **2. Do We Have Candle Data?**
```bash
curl "http://localhost:5000/api/data?symbol=EURUSD.x&timeframe=1H&limit=5"
# Should return array of candles with {time, open, high, low, close, volume}
```

### **3. Do We Have Tick Data?**
```bash
curl http://localhost:5000/api/ticks
# Should return array with latest tick per symbol
```

### **4. Check Database Directly**
```bash
psql -U postgres -d forex_data -c "SELECT COUNT(*) FROM ticks;"
psql -U postgres -d forex_data -c "SELECT COUNT(*) FROM candles_data;"
psql -U postgres -d forex_data -c "SELECT DISTINCT symbol FROM ticks LIMIT 1;"
```

---

## ⚠️ KNOWN ISSUES & IMPROVEMENTS

### **Current Limitations**
1. **Historical Data**: Only GBPJPY setup in main.py (other symbols possible but not configured)
2. **Live Data**: Requires MT5 Terminal with DXN broker installed
3. **Symbols in live_collector.py**: Currently hardcoded (EURUSD.x, GBPUSD.x, NZDUSD.x)
4. **Ticks Table**: No automatic cleanup - will grow indefinitely
5. **candles table**: Legacy table, being replaced by candles_data (partitioned)

### **Potential Improvements**
- [ ] Make symbols configurable via environment variables
- [ ] Add data retention policy for ticks table
- [ ] Add user authentication to API
- [ ] Add more timeframes to CandleGenerator
- [ ] Cache symbols/timeframes API responses
- [ ] Add error recovery for MT5 disconnections
- [ ] Add webhook notifications for price alerts
- [ ] Store technical indicators (RSI, MACD, Bollinger Bands)

---

## 🎯 SUMMARY

**What Works:**
✅ Flask API serving on port 5000  
✅ Live MT5 ticks collection (if MT5 connected)  
✅ Historical OHLC storage in PostgreSQL  
✅ Frontend charts and tables displaying data  
✅ Date range filtering for ticks  

**What Needs Attention:**
❌ Ticks table is empty? → Check if MT5 is connected + running  
❌ Chart has no data? → Run main.py to download GBPJPY history  
❌ Filter not working? → Check browser console for errors, check API logs  

---

**Now ready to debug the actual issue! 🔧**



"""
Forex Dashboard API Server
Flask application for serving real-time and historical forex market data.
Integrates with MT5 collector for live tick data collection.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, render_template, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from src.live_collector import MT5LiveCollector
import threading
import logging
from functools import lru_cache
from datetime import datetime, timedelta
import time

app = Flask(__name__)

# Compression for faster responses
try:
    from flask_compress import Compress
    Compress(app)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "user": "postgres",
    "password": "root",
    "database": "forex_data"
}

# ===== FAST CACHE FOR LIVE DATA =====
class FastCache:
    def __init__(self, ttl_ms=300):  # 300ms TTL
        self.cache = {}
        self.ttl = ttl_ms / 1000.0
        
    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return data
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())

live_cache = FastCache(ttl_ms=150)  # Fast 150ms cache for live views

# Global MT5 collector instance
mt5_collector: MT5LiveCollector | None = None


def get_db():
    """Establish database connection"""
    return psycopg2.connect(**DB_CONFIG)


def get_live_symbols_for_collection():
    """Resolve symbols for MT5 live collection from DB, fallback to defaults."""
    default_symbols = ["EURUSD.x", "GBPUSD.x", "NZDUSD.x"]
    try:
        conn = get_db()
        cur = conn.cursor()

        # Prefer candle symbols (usually full configured set).
        cur.execute("""
            SELECT DISTINCT symbol
            FROM candles_data
            ORDER BY symbol
            LIMIT 50
        """)
        symbols = [r[0] for r in cur.fetchall() if r and r[0]]

        if not symbols:
            cur.execute("""
                SELECT DISTINCT symbol
                FROM ticks
                ORDER BY symbol
                LIMIT 50
            """)
            symbols = [r[0] for r in cur.fetchall() if r and r[0]]

        cur.close()
        conn.close()

        if symbols:
            logger.info("Using %d symbols for live collection", len(symbols))
            return symbols
    except Exception as e:
        logger.warning("Could not load live symbols from DB, using defaults: %s", e)

    return default_symbols


def init_mt5_collector():
    """Initialize MT5 collector in background to prevent blocking Flask startup"""
    global mt5_collector

    def init_in_background():
        global mt5_collector
        try:
            symbols = get_live_symbols_for_collection()
            pool_size = max(30, len(symbols) * 4)
            mt5_collector = MT5LiveCollector(DB_CONFIG, symbols, pool_size=pool_size)
            
            if mt5_collector.mt5_initialized:
                mt5_collector.start_collection(
                    timeframes=['1m', '5m', '15m', '30m', '1H', '4H', '1D'],
                    interval=30,
                    fill_gaps=True
                )
                logger.info("MT5 collector started successfully")
            else:
                logger.warning("MT5 Terminal not available - using database fallback for tick data")
        except Exception as e:
            logger.error(f"MT5 collector initialization error: {e}")

    t = threading.Thread(target=init_in_background, daemon=True)
    t.start()
    logger.info("MT5 initialization thread started")


@app.route("/")
def index():
    """Redirect to main dashboard page"""
    return render_template("tick.html", page="tick")


@app.route("/tick")
def tick_page():
    """Render live tick data page"""
    return render_template("tick.html", page="tick")


@app.route("/history")
def history_page():
    """Render historical data page"""
    return render_template("history.html", page="history")

@app.route("/chart")
def chart_page():
    """Render chart view page"""
    return render_template("chart.html", page="chart")


@app.route("/api/symbols")
def get_symbols():
    """Retrieve list of available symbols from both live ticks and historical candles."""
    # Cache symbols for 5 seconds - they don't change often
    cached = live_cache.get("symbols")
    if cached:
        return jsonify(cached)
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol
            FROM (
                SELECT DISTINCT symbol FROM ticks
                UNION
                SELECT DISTINCT symbol FROM candles_data
            ) symbols
            ORDER BY symbol
        """)
        rows = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        
        live_cache.set("symbols", rows)
        return jsonify(rows)
    except psycopg2.Error as e:
        logger.error(f"Error fetching symbols: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeframes")
def get_timeframes():
    """Retrieve available timeframes with proper chronological ordering"""
    order_map = {
        "1m": 1, "5m": 2, "10m": 3, "15m": 4, "30m": 5,
        "1H": 6, "2H": 7, "4H": 8, "8H": 9, "12H": 10,
        "1D": 11, "1W": 12, "1M": 13
    }
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT timeframe FROM candles_data")
        tfs = list({r[0] for r in cur.fetchall()}) or ["1H", "4H", "1D"]
        cur.close()
        conn.close()
        tfs.sort(key=lambda x: order_map.get(x, 99))
        return jsonify(tfs)
    except psycopg2.Error as e:
        logger.error(f"Error fetching timeframes: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/data")
def get_data():
    """Retrieve historical candle data with deduplication by datetime - OPTIMIZED"""
    symbol = request.args.get("symbol", "EURUSD.x")
    timeframe = request.args.get("timeframe", "1H")
    limit = int(request.args.get("limit", 500))  # Reduced from 10000 to 500
    
    # Cap maximum limit to prevent slow queries
    if limit > 2000:
        limit = 2000

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # OPTIMIZED: Use DISTINCT ON and order by time DESC for faster retrieval
        cur.execute("""
            SELECT * FROM (
                SELECT DISTINCT ON (datetime)
                    time_epoch AS time,
                    open, high, low, close, volume
                FROM candles_data
                WHERE symbol=%s AND timeframe=%s
                ORDER BY datetime DESC
                LIMIT %s
            ) t
            ORDER BY time ASC
        """, (symbol, timeframe, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        # Add cache headers for 1 minute
        response = jsonify([dict(r) for r in rows])
        response.headers['Cache-Control'] = 'public, max-age=60'
        return response
    except psycopg2.Error as e:
        logger.error(f"Error fetching candle data: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/latest")
def get_latest():
    """Retrieve the latest candle for specified symbol and timeframe"""
    symbol = request.args.get("symbol", "EURUSD.x")
    timeframe = request.args.get("timeframe", "1H")

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT time_epoch AS time,
                   open, high, low, close, volume
            FROM candles_data
            WHERE symbol=%s AND timeframe=%s
            ORDER BY datetime DESC
            LIMIT 1
        """, (symbol, timeframe))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return jsonify(dict(row))
        return jsonify({"error": "no data"}), 404
    except psycopg2.Error as e:
        logger.error(f"Error fetching latest candle: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tick")
def get_tick():
    """Get current tick data from MT5 or database fallback"""
    symbol = request.args.get("symbol", "EURUSD.x")
    global mt5_collector

    try:
        # Fast path: serve from in-memory collector cache.
        if mt5_collector and mt5_collector.mt5_initialized:
            cached_tick = mt5_collector.get_latest_tick_snapshot(symbol)
            if cached_tick:
                return jsonify(cached_tick)

            tick = mt5_collector.get_current_tick(symbol)
            if tick:
                return jsonify(tick)

        # Fall back to database
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                CAST(EXTRACT(EPOCH FROM tick_time) AS bigint) AS time,
                symbol, bid, ask, spread
            FROM ticks
            WHERE symbol=%s
            ORDER BY tick_time DESC
            LIMIT 1
        """, (symbol,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return jsonify(dict(row))
        return jsonify({"error": "no tick data"}), 404
        
    except Exception as e:
        logger.error(f"Error fetching tick: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ticks")
def get_ticks():
    """Retrieve latest tick per symbol for live table."""
    limit = int(request.args.get("limit", 100))

    if limit > 500:
        limit = 500
    
    # Try cache first (300ms TTL)
    cache_key = f"ticks_{limit}"
    cached = live_cache.get(cache_key)
    if cached:
        return jsonify(cached)

    global mt5_collector
    if mt5_collector and mt5_collector.mt5_initialized:
        cached_rows = mt5_collector.get_latest_ticks_snapshot()
        if cached_rows:
            result = cached_rows[:limit]
            live_cache.set(cache_key, result)
            return jsonify(result)
    
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                latest.time,
                latest.symbol,
                latest.bid,
                latest.ask,
                latest.spread
            FROM (
                SELECT DISTINCT ON (symbol)
                    CAST(EXTRACT(EPOCH FROM tick_time) AS bigint) AS time,
                    symbol,
                    bid,
                    ask,
                    spread,
                    tick_time
                FROM ticks
                ORDER BY symbol, tick_time DESC
            ) AS latest
            ORDER BY latest.tick_time DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        result = [dict(r) for r in rows]
        live_cache.set(cache_key, result)  # Store in cache
        return jsonify(result)
    except psycopg2.Error as e:
        logger.error(f"Error fetching ticks: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ticks/history")
def get_tick_history():
    """Retrieve historical tick data with optional symbol, year, and date range filtering"""
    symbol = request.args.get("symbol")
    year = request.args.get("year")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = int(request.args.get("limit", 200))

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT 
                CAST(EXTRACT(EPOCH FROM tick_time) AS bigint) AS time, 
                symbol, bid, ask, spread 
            FROM ticks
        """
        
        where_clauses = []
        params = []

        # Add symbol filter
        if symbol:
            where_clauses.append("symbol = %s")
            params.append(symbol)

        # Add year filter - extract year from tick_time
        if year:
            where_clauses.append("EXTRACT(YEAR FROM tick_time) = %s")
            params.append(int(year))

        # Add date range filters
        if start_date:
            where_clauses.append("DATE(tick_time) >= %s::date")
            params.append(start_date)
        
        if end_date:
            where_clauses.append("DATE(tick_time) <= %s::date")
            params.append(end_date)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY tick_time DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify([dict(r) for r in rows])
        
    except Exception as e:
        logger.error(f"Error fetching tick history: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/status")
def get_status():
    """Get MT5 collector status and connection information"""
    global mt5_collector

    status = {
        "status": "running",
        "mt5_connected": mt5_collector.mt5_initialized if mt5_collector else False,
        "symbols": mt5_collector.symbols if mt5_collector else []
    }

    return jsonify(status)


@app.route("/api/debug/ticks-count")
def debug_ticks_count():
    """Debug endpoint: Display tick data statistics and date range"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT COUNT(*) as total FROM ticks")
        total = cur.fetchone()['total']
        
        cur.execute("SELECT MIN(tick_time) as earliest, MAX(tick_time) as latest FROM ticks")
        date_range = cur.fetchone()
        
        cur.execute("SELECT DISTINCT symbol FROM ticks ORDER BY symbol")
        symbols = [row['symbol'] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return jsonify({
            "total_ticks": total,
            "earliest_date": str(date_range['earliest']) if date_range['earliest'] else None,
            "latest_date": str(date_range['latest']) if date_range['latest'] else None,
            "symbols": symbols
        })
    except Exception as e:
        logger.error(f"Error in debug ticks count: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/debug/mt5-status")
def debug_mt5_status():
    """Debug endpoint: Display MT5 collector status"""
    global mt5_collector
    
    return jsonify({
        "mt5_collector_exists": mt5_collector is not None,
        "mt5_initialized": mt5_collector.mt5_initialized if mt5_collector else False,
        "mt5_running": mt5_collector.running if mt5_collector else False,
        "symbols": mt5_collector.symbols if mt5_collector else []
    })



@app.route("/test")
def test():
    """Health check endpoint"""
    return "Server is running", 200


@app.route("/api/history/candles")
def get_candles_history():
    """Retrieve historical candle data with efficient optional filters."""
    symbol = request.args.get("symbol", "EURUSD.x")
    timeframe = request.args.get("timeframe", "1H")
    year = request.args.get("year")
    month = request.args.get("month")
    date = request.args.get("date")
    limit = int(request.args.get("limit", 500))
    before_time = request.args.get("before_time")
    
    # Cap maximum limit
    if limit > 2000:
        limit = 2000

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT 
                datetime,
                symbol,
                time_epoch AS time,
                open, high, low, close, volume
            FROM candles_data
            WHERE symbol=%s AND timeframe=%s
        """
        params = [symbol, timeframe]

        # Prefer range predicates so index on (symbol, timeframe, datetime) stays usable.
        if date:
            query += " AND datetime >= %s::date AND datetime < (%s::date + INTERVAL '1 day')"
            params.extend([date, date])
        else:
            if year:
                year_int = int(year)
                query += " AND datetime >= %s::timestamp AND datetime < %s::timestamp"
                params.extend([f"{year_int:04d}-01-01", f"{year_int + 1:04d}-01-01"])

            if month:
                month_int = int(month)
                if month_int < 1 or month_int > 12:
                    return jsonify({"error": "Invalid month filter"}), 400

                if year:
                    start_dt = datetime(int(year), month_int, 1)
                    if month_int == 12:
                        end_dt = datetime(int(year) + 1, 1, 1)
                    else:
                        end_dt = datetime(int(year), month_int + 1, 1)
                    query += " AND datetime >= %s AND datetime < %s"
                    params.extend([start_dt, end_dt])
                else:
                    query += " AND EXTRACT(MONTH FROM datetime) = %s"
                    params.append(month_int)

        if before_time:
            try:
                before_time_int = int(before_time)
                query += " AND time_epoch < %s"
                params.append(before_time_int)
            except ValueError:
                return jsonify({"error": "Invalid before_time cursor"}), 400

        fetch_limit = limit + 1
        query += " ORDER BY datetime DESC LIMIT %s"
        params.append(fetch_limit)

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_before_time = rows[-1]["time"] if has_more and rows else None

        response = jsonify([dict(r) for r in rows])
        response.headers['Cache-Control'] = 'public, max-age=60'
        response.headers['X-Has-More'] = '1' if has_more else '0'
        if next_before_time is not None:
            response.headers['X-Next-Before-Time'] = str(next_before_time)
        return response
    except Exception as e:
        logger.error(f"Error fetching candles history: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/symbols")
def get_history_symbols():
    """Retrieve symbols that actually have candle history data."""
    timeframe = request.args.get("timeframe", "1H")

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT DISTINCT symbol
            FROM candles_data
            WHERE timeframe = %s
            ORDER BY symbol
        """, (timeframe,))
        rows = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify(rows)
    except psycopg2.Error as e:
        logger.error(f"Error fetching history symbols: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/dates-available")
def get_available_dates():
    """Get available years and months for historical data, optionally narrowed by year."""
    symbol = request.args.get("symbol", "EURUSD.x")
    timeframe = request.args.get("timeframe", "1H")
    year = request.args.get("year")

    selected_year = None
    if year:
        try:
            selected_year = int(year)
        except ValueError:
            return jsonify({"error": "Invalid year filter"}), 400

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get available years
        cur.execute("""
            SELECT DISTINCT EXTRACT(YEAR FROM datetime)::integer as year
            FROM candles_data
            WHERE symbol=%s AND timeframe=%s
            ORDER BY year DESC
        """, (symbol, timeframe))
        years = [row['year'] for row in cur.fetchall()]

        # Get available months (optionally narrowed to selected year)
        month_query = """
            SELECT DISTINCT EXTRACT(MONTH FROM datetime)::integer as month
            FROM candles_data
            WHERE symbol=%s AND timeframe=%s
        """
        month_params = [symbol, timeframe]

        if selected_year is not None:
            month_query += " AND datetime >= %s::timestamp AND datetime < %s::timestamp"
            month_params.extend([
                f"{selected_year:04d}-01-01",
                f"{selected_year + 1:04d}-01-01"
            ])

        month_query += " ORDER BY month"
        cur.execute(month_query, tuple(month_params))
        months = [row['month'] for row in cur.fetchall()]

        # Get date range (optionally narrowed to selected year)
        date_range_query = """
            SELECT MIN(DATE(datetime)) as min_date, MAX(DATE(datetime)) as max_date
            FROM candles_data
            WHERE symbol=%s AND timeframe=%s
        """
        date_range_params = [symbol, timeframe]

        if selected_year is not None:
            date_range_query += " AND datetime >= %s::timestamp AND datetime < %s::timestamp"
            date_range_params.extend([
                f"{selected_year:04d}-01-01",
                f"{selected_year + 1:04d}-01-01"
            ])

        cur.execute(date_range_query, tuple(date_range_params))
        date_range = cur.fetchone()

        cur.close()
        conn.close()

        return jsonify({
            "years": years,
            "months": months,
            "selected_year": selected_year,
            "min_date": str(date_range['min_date']) if date_range['min_date'] else None,
            "max_date": str(date_range['max_date']) if date_range['max_date'] else None
        })
    except Exception as e:
        logger.error(f"Error fetching available dates: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/data-info")
def get_data_info():
    """Get statistics for candle data (count, date range, average volume)"""
    symbol = request.args.get("symbol", "EURUSD.x")
    timeframe = request.args.get("timeframe", "1H")

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*), MIN(datetime), MAX(datetime), AVG(volume)
            FROM candles_data
            WHERE symbol=%s AND timeframe=%s
        """, (symbol, timeframe))
        r = cur.fetchone()
        cur.close()
        conn.close()

        return jsonify({
            "symbol": symbol,
            "timeframe": timeframe,
            "total_candles": r[0],
            "first_candle": r[1].isoformat() if r[1] else None,
            "last_candle": r[2].isoformat() if r[2] else None,
            "avg_volume": float(r[3]) if r[3] else 0
        })
    except Exception as e:
        logger.error(f"Error fetching data info: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_mt5_collector()
    app.run(debug=False, port=5000, use_reloader=False)


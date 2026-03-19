

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

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "user": "postgres",
    "password": "root",
    "database": "forex_data"
}

# Global MT5 collector instance
mt5_collector: MT5LiveCollector | None = None


def get_db():
    """Establish database connection"""
    return psycopg2.connect(**DB_CONFIG)


def init_mt5_collector():
    """Initialize MT5 collector in background to prevent blocking Flask startup"""
    global mt5_collector

    def init_in_background():
        global mt5_collector
        try:
            symbols = ["EURUSD.x", "GBPUSD.x", "NZDUSD.x"]
            mt5_collector = MT5LiveCollector(DB_CONFIG, symbols)
            
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
    """Render main dashboard page"""
    return render_template("index.html")


@app.route("/api/symbols")
def get_symbols():
    """Retrieve list of available trading symbols from database"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM candles_data ORDER BY symbol")
        rows = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
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
    """Retrieve historical candle data with deduplication by datetime"""
    symbol = request.args.get("symbol", "EURUSD.x")
    timeframe = request.args.get("timeframe", "1H")
    limit = int(request.args.get("limit", 10000))

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
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
        return jsonify([dict(r) for r in rows])
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
        # Try MT5 first if available
        if mt5_collector and mt5_collector.mt5_initialized:
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
    """Retrieve latest tick data for all symbols"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT DISTINCT ON (symbol)
                CAST(EXTRACT(EPOCH FROM tick_time) AS bigint) AS time,
                symbol, bid, ask, mid, spread
            FROM ticks
            ORDER BY symbol, tick_time DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except psycopg2.Error as e:
        logger.error(f"Error fetching ticks: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ticks/history")
def get_tick_history():
    """Retrieve historical tick data with optional symbol and date range filtering"""
    symbol = request.args.get("symbol")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = int(request.args.get("limit", 1000))

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
        if symbol and symbol != "ALL":
            where_clauses.append("symbol = %s")
            params.append(symbol)

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


@app.route("/ticks")
def ticks_page():
    """Render ticks data visualization page"""
    return render_template("ticks.html")


@app.route("/test")
def test():
    """Health check endpoint"""
    return "Server is running", 200


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


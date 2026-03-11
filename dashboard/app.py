import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, render_template, request, jsonify, Response
import psycopg2
from psycopg2.extras import RealDictCursor
from src.live_collector import MT5LiveCollector
import threading
import logging
import json
import time

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host":     "localhost",
    "user":     "postgres",
    "password": "root",
    "database": "forex_data"
}

# Global MT5 collector (shared across requests)
mt5_collector: MT5LiveCollector | None = None


def get_db():
    return psycopg2.connect(**DB_CONFIG)


def init_mt5_collector():
    """App startup par background mein MT5 collector shuru karo."""
    global mt5_collector
    symbols = ["EURUSD.x", "GBPUSD.x", "NZDUSD.x"]
    mt5_collector = MT5LiveCollector(DB_CONFIG, symbols)

    t = threading.Thread(
        target=mt5_collector.start_collection,
        kwargs=dict(
            timeframes=['1m','5m','15m','30m','1H','4H','1D'],
            interval=30,
            fill_gaps=True
        ),
        daemon=True
    )
    t.start()
    logger.info("✅ MT5 collector background thread started")


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/symbols")
def get_symbols():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM candles ORDER BY symbol")
        rows = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify(rows)
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeframes")
def get_timeframes():
    order_map = {
        "1m":1,"5m":2,"10m":3,"15m":4,"30m":5,
        "1H":6,"2H":7,"4H":8,"8H":9,"12H":10,
        "1D":11,"1W":12,"1M":13
    }
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT DISTINCT timeframe FROM candles")
        tfs  = list({r[0] for r in cur.fetchall()}) or ["1H","4H","1D"]
        cur.close(); conn.close()
        tfs.sort(key=lambda x: order_map.get(x, 99))
        return jsonify(tfs)
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/data")
def get_data():
    """Historical + live candles (deduplicated, strictly ascending time)."""
    symbol    = request.args.get("symbol",    "EURUSD")
    timeframe = request.args.get("timeframe", "1H")
    limit     = int(request.args.get("limit", 10000))

    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=RealDictCursor)
        # Use subquery with DISTINCT ON to remove duplicate epoch seconds
        cur.execute("""
            SELECT * FROM (
                SELECT DISTINCT ON (time)
                    CAST(EXTRACT(EPOCH FROM datetime) AS bigint) AS time,
                    open, high, low, close, volume
                FROM candles
                WHERE symbol=%s AND timeframe=%s
                ORDER BY time DESC, datetime DESC
                LIMIT %s
            ) t ORDER BY time ASC
        """, (symbol, timeframe, limit))
        rows = cur.fetchall()
        cur.close(); conn.close()
        logger.info(f"Chart data: {len(rows)} bars for {symbol} {timeframe}")
        return jsonify([dict(r) for r in rows])
    except psycopg2.Error as e:
        logger.error(e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/latest")
def get_latest():
    """Latest candle bar from DB (updates every ~30s when market is open)."""
    symbol    = request.args.get("symbol",    "EURUSD")
    timeframe = request.args.get("timeframe", "1H")
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT CAST(EXTRACT(EPOCH FROM datetime) AS bigint) AS time,
                   open, high, low, close, volume
            FROM candles
            WHERE symbol=%s AND timeframe=%s
            ORDER BY datetime DESC LIMIT 1
        """, (symbol, timeframe))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            return jsonify(dict(row))
        return jsonify({"error": "no data"}), 404
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tick")
def get_tick():
    """
    Instant LIVE bid/ask price from MT5 symbol_info_tick.
    Updates instantly (no DB involved) – used for the real-time price header.
    """
    symbol = request.args.get("symbol", "EURUSD")
    global mt5_collector
    if mt5_collector is None or not mt5_collector.mt5_initialized:
        return jsonify({"error": "MT5 not connected"}), 503
    tick = mt5_collector.get_current_tick(symbol)
    if tick is None:
        return jsonify({"error": f"No tick for {symbol}"}), 404
    return jsonify(tick)


@app.route("/api/status")
def get_status():
    global mt5_collector
    if mt5_collector and mt5_collector.running:
        return jsonify({
            "status":    "running",
            "connected": mt5_collector.mt5_initialized,
            "symbols":   mt5_collector.symbols
        })
    return jsonify({"status": "stopped", "connected": False})


@app.route("/api/data-info")
def get_data_info():
    symbol    = request.args.get("symbol",    "EURUSD")
    timeframe = request.args.get("timeframe", "1H")
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT COUNT(*), MIN(datetime), MAX(datetime), AVG(volume)
            FROM candles WHERE symbol=%s AND timeframe=%s
        """, (symbol, timeframe))
        r = cur.fetchone()
        cur.close(); conn.close()
        return jsonify({
            "symbol": symbol, "timeframe": timeframe,
            "total_candles": r[0],
            "first_candle":  r[1].isoformat() if r[1] else None,
            "last_candle":   r[2].isoformat() if r[2] else None,
            "avg_volume":    float(r[3]) if r[3] else 0
        })
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_mt5_collector()
    app.run(debug=False, port=5000, use_reloader=False)
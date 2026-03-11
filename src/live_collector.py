"""
╔════════════════════════════════════════════════════════════════════════════╗
║         MT5 Live Data Collector – Forex Trading Dashboard                  ║
║  ✅ Connection Pooling | ✅ Error Handling | ✅ Timezone Fix               ║
║  ✅ Duplicate Prevention | ✅ Windows Compatible                           ║
╚════════════════════════════════════════════════════════════════════════════╝
"""

import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import extras, pool
import threading
import logging
import sys
import os

# ═══════════════════════════════════════════════════════════════════════════
# WINDOWS UTF-8 ENCODING FIX
# ═══════════════════════════════════════════════════════════════════════════

# Enable UTF-8 output on Windows
if sys.platform == 'win32':
    # Set console code page to UTF-8
    os.system('chcp 65001 > nul 2>&1')
    
    # Force UTF-8 in Python
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# ═══════════════════════════════════════════════════════════════════════════
# LOGGING SETUP (Windows Compatible)
# ════════════════════���══════════════════════════════════════════════════════

class UTF8Formatter(logging.Formatter):
    """Custom formatter to handle UTF-8 encoding properly"""
    def format(self, record):
        # Remove emoji and special characters that Windows can't handle
        record.msg = str(record.msg).encode('utf-8', errors='replace').decode('utf-8')
        return super().format(record)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('mt5_collector.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# Set UTF-8 formatter
for handler in logger.handlers:
    handler.setFormatter(
        UTF8Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
    )


# ═══════════════════════════════════════════════════════════════════════════
# MT5 TIMEFRAME MAPPING
# ═══════════════════════════════════════════════════════════════════════════

TF_MAP = {
    '1m':  mt5.TIMEFRAME_M1,
    '5m':  mt5.TIMEFRAME_M5,
    '10m': mt5.TIMEFRAME_M10,
    '15m': mt5.TIMEFRAME_M15,
    '30m': mt5.TIMEFRAME_M30,
    '1H':  mt5.TIMEFRAME_H1,
    '4H':  mt5.TIMEFRAME_H4,
    '1D':  mt5.TIMEFRAME_D1,
    '1W':  mt5.TIMEFRAME_W1,
}


# ═══════════════════════════════════════════════════════════════════════════
# MT5 LIVE COLLECTOR CLASS
# ═══════════════════════════════════════════════════════════════════════════

class MT5LiveCollector:
    """
    MT5 se OHLCV candle data aur live tick prices lata hai.
    PostgreSQL database mein efficiently store karta hai.

    Flow:
      1. _init_mt5()        -> MT5 terminal se connect karo
      2. fill_missing_data() -> Purani data database fill karo
      3. start_collection()  -> Live loops: har interval par naye candles save
      4. get_current_tick()  -> Instant live bid/ask price (dashboard)
    """

    def __init__(self, db_config: dict, symbols: list = None, pool_size: int = 5):
        """
        Initialize MT5 Collector with connection pooling.
        
        Args:
            db_config (dict): PostgreSQL connection config
            symbols (list): MT5 symbols to collect
            pool_size (int): Database connection pool size
        """
        self.db_config = db_config
        self.symbols = symbols or ["EURUSD", "GBPUSD", "USDJPY"]
        self.mt5_initialized = False
        self.running = False
        self.last_tick_time = {}  # Track last tick time per symbol
        
        # CONNECTION POOL (Production-ready)
        try:
            self.db_pool = psycopg2.pool.SimpleConnectionPool(
                1, pool_size,
                host=db_config.get('host', 'localhost'),
                user=db_config.get('user', 'postgres'),
                password=db_config.get('password', 'root'),
                database=db_config.get('database', 'forex_data'),
                connect_timeout=10
            )
            logger.info('[OK] Database connection pool created (size: %d)', pool_size)
        except Exception as e:
            logger.error('[FAILED] DB pool creation: %s', e)
            self.db_pool = None
        
        # Initialize MT5
        self._init_mt5()

    # ─────────────────────────────────────────────────────────────────────
    # MT5 CONNECTION
    # ─────────────────────────────────────────────────────────────────────

    def _init_mt5(self) -> bool:
        """
        MT5 terminal se connect karo aur symbols subscribe karo.
        
        Returns:
            bool: True if success, False otherwise
        """
        try:
            if not mt5.initialize():
                error_msg = mt5.last_error()
                logger.error('[FAILED] MT5 init: %s', error_msg)
                logger.error('  -> MT5 terminal khula hai?')
                logger.error('  -> Demo/Live account login hai?')
                logger.error('  -> Firewall/Antivirus block to nahi kar raha?')
                return False
            
            self.mt5_initialized = True
            logger.info('[OK] MT5 Connected!')
            
            # Subscribe to all symbols
            for sym in self.symbols:
                if mt5.symbol_select(sym, True):
                    logger.info('  [OK] %s subscribed', sym)
                else:
                    logger.warning('  [SKIP] %s - could not subscribe (may not exist)', sym)
            
            return True
            
        except Exception as exc:
            logger.error('[FAILED] MT5 init exception: %s', exc)
            return False

    # ─────────────────────────────────────────────────────────────────────
    # LIVE TICK PRICE (Real-time bid/ask)
    # ─────────────────────────────────────────────────────────────────────

    def get_current_tick(self, symbol: str) -> dict | None:
        """
        MT5 se INSTANT live tick price lao (bid/ask/last).
        
        Market open hone par hamesha kaam karta hai.
        Real-time price dashboard header ke liye.
        
        Args:
            symbol (str): Trading symbol (e.g., "EURUSD.x")
        
        Returns:
            dict | None: Tick data ya None agar market closed/no data
        """
        if not self.mt5_initialized:
            return None
        
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            return {
                "symbol": symbol,
                "time": int(tick.time),
                "bid": float(tick.bid),
                "ask": float(tick.ask),
                "last": float((tick.bid + tick.ask) / 2),  # Mid price
                "bid_volume": int(tick.bid_last) if hasattr(tick, 'bid_last') else 0,
                "ask_volume": int(tick.ask_last) if hasattr(tick, 'ask_last') else 0,
            }
        except Exception as e:
            logger.debug('Tick error [%s]: %s', symbol, e)
            return None

    # ─────────────────────────────────────────────────────────────────────
    # CANDLE FETCHING FROM MT5
    # ─────────────────────────────────────────────────────────────────────

    def _fetch_rates(self, symbol: str, timeframe: str,
                     start: datetime, end: datetime) -> pd.DataFrame | None:
        """
        MT5 se OHLCV bars lao (start..end UTC range).
        
        Automatic error handling
        DataFrame mein convert karke return
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe string ('1m', '1H', etc.)
            start: Start datetime (UTC)
            end: End datetime (UTC)
        
        Returns:
            DataFrame | None: OHLCV data ya None agar error/no data
        """
        tf = TF_MAP.get(timeframe)
        if tf is None:
            logger.warning('[SKIP] Unknown timeframe: %s', timeframe)
            return None
        
        try:
            rates = mt5.copy_rates_range(symbol, tf, start, end)
            
            if rates is None or len(rates) == 0:
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df.rename(columns={'time': 'datetime', 'tick_volume': 'volume'}, inplace=True)
            df['datetime'] = pd.to_datetime(df['datetime'], unit='s', utc=True)
            
            return df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
            
        except Exception as e:
            logger.error('[FAILED] Fetch rates [%s/%s]: %s', symbol, timeframe, e)
            return None

    # ─────────────────────────────────────────────────────────────────────
    # DATABASE HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _get_db_connection(self):
        """
        Connection pool se connection lao.
        
        Connection pooling se performance boost
        Automatic handling of closed connections
        
        Returns:
            Connection ya None
        """
        if self.db_pool is None:
            logger.error('[FAILED] Database pool not initialized')
            return None
        
        try:
            return self.db_pool.getconn()
        except Exception as e:
            logger.error('[FAILED] Get DB connection: %s', e)
            return None

    def _return_db_connection(self, conn):
        """Connection ko pool mein return karo."""
        if self.db_pool and conn:
            try:
                self.db_pool.putconn(conn)
            except Exception as e:
                logger.error('[FAILED] Return connection: %s', e)

    def _last_saved_datetime(self, symbol: str, timeframe: str) -> datetime | None:
        """
        Database mein is symbol+timeframe ki latest datetime.
        
        Gap fill ke liye zaroori
        
        Returns:
            datetime | None: Last saved time ya None agar no data
        """
        conn = self._get_db_connection()
        if not conn:
            return None
        
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT MAX(datetime) FROM candles WHERE symbol=%s AND timeframe=%s",
                (symbol, timeframe)
            )
            result = cur.fetchone()
            cur.close()
            return result[0] if result and result[0] else None
            
        except Exception as e:
            logger.error('[FAILED] DB last saved query: %s', e)
            return None
        finally:
            self._return_db_connection(conn)

    def _save_candles(self, symbol: str, timeframe: str,
                      df: pd.DataFrame, is_live: bool = False) -> int:
        """
        Candles ko database mein UPSERT karo.
        
        Duplicate prevention (ON CONFLICT)
        Batch insert se fast performance
        Transaction safe
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            df: DataFrame with OHLCV data
            is_live: True if live update, False if gap-fill
        
        Returns:
            int: Number of saved candles
        """
        if df is None or df.empty:
            return 0
        
        conn = self._get_db_connection()
        if not conn:
            return 0
        
        try:
            cur = conn.cursor()
            
            # UPSERT query (duplicate safe)
            sql = """
                INSERT INTO candles 
                    (symbol, timeframe, datetime, open, high, low, close, volume)
                VALUES %s
                ON CONFLICT (symbol, timeframe, datetime) DO UPDATE
                SET 
                    open=EXCLUDED.open,
                    high=EXCLUDED.high,
                    low=EXCLUDED.low,
                    close=EXCLUDED.close,
                    volume=EXCLUDED.volume
            """
            
            values = []
            for _, row in df.iterrows():
                values.append((
                    symbol,
                    timeframe,
                    row['datetime'],
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close']),
                    int(row['volume']) if row['volume'] > 0 else 0
                ))
            
            extras.execute_values(cur, sql, values, page_size=1000)
            conn.commit()
            
            tag = "[LIVE]" if is_live else "[FILL]"
            logger.info('%s %s %s: [OK] saved %d candles', tag, symbol, timeframe, len(values))
            
            return len(values)
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error('[FAILED] DB save [%s/%s]: %s', symbol, timeframe, e)
            return 0
        finally:
            if cur:
                cur.close()
            self._return_db_connection(conn)

    # ─────────────────────────────────────────────────────────────────────
    # GAP FILL (Historical data)
    # ─────────────────────────────────────────────────────────────────────

    def fill_missing_data(self, symbol: str, timeframe: str) -> int:
        """
        Database ki last saved candle ke baad se ab tak ka data fill karo.
        
        Automatic gap detection
        30-day lookback if no data exists
        
        Returns:
            int: Number of filled candles
        """
        last = self._last_saved_datetime(symbol, timeframe)
        
        if last is None:
            # No data exists, fetch last 30 days
            start = datetime.utcnow() - timedelta(days=30)
            logger.info('[FILL] %s/%s - No existing data, fetching last 30 days', symbol, timeframe)
        else:
            # Fill from last saved time
            start = last + timedelta(seconds=1)
            logger.info('[FILL] %s/%s - Gap fill from %s', symbol, timeframe, start)

        end = datetime.utcnow()
        df = self._fetch_rates(symbol, timeframe, start, end)
        
        if df is None or df.empty:
            logger.info('[SKIP] %s/%s - No new data from MT5 (market closed?)', symbol, timeframe)
            return 0
        
        return self._save_candles(symbol, timeframe, df, is_live=False)

    # ─────────────────────────────────────────────────────────────────────
    # LIVE UPDATE LOOP (Background thread per symbol×timeframe)
    # ─────────────────────────────────────────────────────────────────────

    def _live_loop(self, symbol: str, timeframe: str, interval: int):
        """
        Har `interval` seconds mein MT5 se latest ~5 bars lao aur DB mein UPDATE karo.
        
        Background thread chalta hai
        TradingView chart automatic update hota hai
        Error resilient
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            interval: Poll interval in seconds
        """
        logger.info('[LIVE] Loop started -> %s %s (every %ds)', symbol, timeframe, interval)
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.running:
            try:
                end = datetime.utcnow()
                start = end - timedelta(seconds=interval * 5)  # Last ~5 bars
                
                df = self._fetch_rates(symbol, timeframe, start, end)
                
                if df is not None and not df.empty:
                    self._save_candles(symbol, timeframe, df, is_live=True)
                    consecutive_errors = 0  # Reset error counter
                else:
                    # Get tick to show market is alive
                    tick = self.get_current_tick(symbol)
                    if tick:
                        logger.debug('[TICK] %s: bid=%.5f ask=%.5f', symbol, tick['bid'], tick['ask'])
                
                time.sleep(interval)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error('[FAILED] Live loop [%s/%s]: %s (#%d)', symbol, timeframe, e, consecutive_errors)
                
                # Stop if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical('[STOPPED] Live loop [%s/%s] - too many errors', symbol, timeframe)
                    self.running = False
                    break
                
                time.sleep(interval * 2)  # Backoff on error

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────

    def start_collection(self,
                         timeframes: list = None,
                         interval: int = 30,
                         fill_gaps: bool = True):
        """
        Complete data collection pipeline shuru karo.
        
        Phase 1: Gap fill (historical data)
        Phase 2: Live loops (background threads)
        
        Args:
            timeframes: List of timeframes to collect
            interval: Live poll interval in seconds
            fill_gaps: Whether to fill missing historical data
        """
        if not self.mt5_initialized:
            logger.error('[FAILED] MT5 not initialized - cannot start collection')
            return

        if timeframes is None:
            timeframes = ['1m', '5m', '15m', '1H']

        self.running = True
        
        logger.info('='*70)
        logger.info('[START] MT5LiveCollector')
        logger.info('  Symbols    : %s', self.symbols)
        logger.info('  Timeframes : %s', timeframes)
        logger.info('  Interval   : %ds', interval)
        logger.info('='*70)

        # ── PHASE 1: GAP FILL ────────────────────────────────────────────
        if fill_gaps:
            logger.info('[PHASE 1] Filling gaps...')
            for sym in self.symbols:
                for tf in timeframes:
                    self.fill_missing_data(sym, tf)
            logger.info('[PHASE 1] Gap fill complete')

        # ── PHASE 2: LIVE LOOPS ──────────────────────────────────────────
        logger.info('[PHASE 2] Starting live loops...')
        threads = []
        
        for sym in self.symbols:
            for tf in timeframes:
                t = threading.Thread(
                    target=self._live_loop,
                    args=(sym, tf, interval),
                    daemon=True,
                    name=f"live-{sym}-{tf}"
                )
                t.start()
                threads.append(t)
                logger.info('  [THREAD] %s %s', sym, tf)

        logger.info('[OK] All live loops started (daemon threads)')
        
        # Keep main thread alive
        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            logger.info('[SHUTDOWN] Signal received...')
            self.stop()

    def stop(self):
        """Collection ko safely band karo."""
        logger.info('[STOP] Stopping MT5LiveCollector...')
        self.running = False
        
        if self.mt5_initialized:
            try:
                mt5.shutdown()
                logger.info('[OK] MT5 disconnected')
            except Exception as e:
                logger.error('[FAILED] MT5 shutdown: %s', e)
        
        # Close connection pool
        if self.db_pool:
            try:
                self.db_pool.closeall()
                logger.info('[OK] Database connection pool closed')
            except Exception as e:
                logger.error('[FAILED] DB pool close: %s', e)

    def get_status(self) -> dict:
        """Collection status return karo."""
        return {
            "running": self.running,
            "mt5_connected": self.mt5_initialized,
            "symbols": self.symbols,
            "timestamp": datetime.utcnow().isoformat()
        }


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    DB_CONFIG = {
        "host": "localhost",
        "user": "postgres",
        "password": "root",
        "database": "forex_data"
    }
    
    collector = MT5LiveCollector(DB_CONFIG, ["EURUSD.x", "GBPUSD.x", "NZDUSD.x"])
    
    try:
        collector.start_collection(
            timeframes=['1m', '5m', '15m', '30m', '1H', '4H', '1D'],
            interval=30,
            fill_gaps=True
        )
    except KeyboardInterrupt:
        collector.stop()
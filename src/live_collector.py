# FINAL SAFE VERSION
# Original logic preserved + missing get_current_tick() added + small safety fixes

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

# ================= WINDOWS UTF8 FIX =================
if sys.platform == 'win32':
    os.system('chcp 65001 > nul 2>&1')
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ================= LOGGING =================
class UTF8Formatter(logging.Formatter):
    def format(self, record):
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

for handler in logger.handlers:
    handler.setFormatter(UTF8Formatter('%(asctime)s - [%(levelname)s] - %(message)s'))

# ================= TIMEFRAME MAP =================
TF_MAP = {
    '1m': mt5.TIMEFRAME_M1,
    '5m': mt5.TIMEFRAME_M5,
    '10m': mt5.TIMEFRAME_M10,
    '15m': mt5.TIMEFRAME_M15,
    '30m': mt5.TIMEFRAME_M30,
    '1H': mt5.TIMEFRAME_H1,
    '4H': mt5.TIMEFRAME_H4,
    '1D': mt5.TIMEFRAME_D1,
    '1W': mt5.TIMEFRAME_W1,
}


class MT5LiveCollector:

    def __init__(self, db_config: dict, symbols: list = None, pool_size: int = 5):

        self.db_config = db_config
        self.symbols = symbols or ["EURUSD", "GBPUSD", "USDJPY"]
        self.mt5_initialized = False
        self.running = False

        try:
            self.db_pool = psycopg2.pool.SimpleConnectionPool(
                1,
                pool_size,
                host=db_config.get('host', 'localhost'),
                user=db_config.get('user', 'postgres'),
                password=db_config.get('password', 'root'),
                database=db_config.get('database', 'forex_data'),
                connect_timeout=10
            )
            logger.info('[OK] Database connection pool created')
        except Exception as e:
            logger.error('[FAILED] DB pool creation: %s', e)
            self.db_pool = None

        self._init_mt5()

# ================= MT5 INIT =================

    def _init_mt5(self) -> bool:
        try:
            if not mt5.initialize():
                logger.error('MT5 init failed: %s', mt5.last_error())
                return False

            self.mt5_initialized = True
            logger.info('[OK] MT5 Connected')

            for sym in self.symbols:
                mt5.symbol_select(sym, True)

            return True

        except Exception as exc:
            logger.error('MT5 init exception: %s', exc)
            return False

# ================= LIVE TICK API (FIXED) =================

    def get_current_tick(self, symbol):
        """Return current MT5 tick (used by Flask /api/tick)"""

        if not self.mt5_initialized:
            return None

        try:
            tick = mt5.symbol_info_tick(symbol)

            if tick is None:
                return None

            bid = float(tick.bid)
            ask = float(tick.ask)

            return {
                "symbol": symbol,
                "time": int(tick.time),
                "bid": bid,
                "ask": ask,
                "last": (bid + ask) / 2
            }

        except Exception as e:
            logger.error("Tick read error %s: %s", symbol, e)
            return None

# ================= DB CONNECTION =================

    def _get_db_connection(self):
        if self.db_pool is None:
            return None
        return self.db_pool.getconn()

    def _return_db_connection(self, conn):
        if self.db_pool and conn:
            self.db_pool.putconn(conn)

# ================= TICK SAVE =================

    def _save_tick(self, symbol, tick):

        conn = self._get_db_connection()
        if not conn:
            return

        try:
            cur = conn.cursor()

            mid = (tick.bid + tick.ask) / 2
            spread = tick.ask - tick.bid

            cur.execute(
                """
                INSERT INTO ticks(symbol, tick_time, bid, ask, mid, spread)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    symbol,
                    datetime.utcfromtimestamp(tick.time),
                    float(tick.bid),
                    float(tick.ask),
                    float(mid),
                    float(spread)
                )
            )

            conn.commit()

        except Exception as e:
            logger.error('Tick insert error: %s', e)
            conn.rollback()

        finally:
            cur.close()
            self._return_db_connection(conn)

# ================= TICK LOOP =================

    def _tick_loop(self, symbol):

        logger.info('[TICK] stream started %s', symbol)

        while self.running:
            try:
                tick = mt5.symbol_info_tick(symbol)

                if tick:
                    self._save_tick(symbol, tick)

                time.sleep(0.2)

            except Exception as e:
                logger.error('Tick loop error %s: %s', symbol, e)
                time.sleep(1)

# ================= EXISTING CANDLE SYSTEM =================

    def _fetch_rates(self, symbol: str, timeframe: str, start: datetime, end: datetime):

        tf = TF_MAP.get(timeframe)
        rates = mt5.copy_rates_range(symbol, tf, start, end)

        if rates is None or len(rates) == 0:
            return None

        df = pd.DataFrame(rates)

        df.rename(columns={'time': 'datetime', 'tick_volume': 'volume'}, inplace=True)
        df['datetime'] = pd.to_datetime(df['datetime'], unit='s', utc=True)

        return df[['datetime', 'open', 'high', 'low', 'close', 'volume']]

# ================= SAVE CANDLES =================

    def _save_candles(self, symbol, timeframe, df):

        if df is None or df.empty:
            return

        conn = self._get_db_connection()

        try:
            cur = conn.cursor()

            sql = """
            INSERT INTO candles
            (symbol,timeframe,datetime,open,high,low,close,volume)
            VALUES %s
            ON CONFLICT(symbol,timeframe,datetime)
            DO UPDATE SET
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
                    row.datetime,
                    float(row.open),
                    float(row.high),
                    float(row.low),
                    float(row.close),
                    float(row.volume)
                ))

            extras.execute_values(cur, sql, values)

            conn.commit()

        except Exception as e:
            logger.error('Candle save error: %s', e)
            conn.rollback()

        finally:
            cur.close()
            self._return_db_connection(conn)

# ================= LIVE LOOP =================

    def _live_loop(self, symbol, timeframe, interval):

        while self.running:

            try:

                end = datetime.utcnow()
                start = end - timedelta(seconds=interval * 5)

                df = self._fetch_rates(symbol, timeframe, start, end)

                if df is not None:
                    self._save_candles(symbol, timeframe, df)

                time.sleep(interval)

            except Exception as e:

                logger.error('Live loop error %s %s: %s', symbol, timeframe, e)
                time.sleep(interval)

# ================= START =================

    def start_collection(self, timeframes=None, interval=30, fill_gaps=True):

        if not self.mt5_initialized:
            logger.error('MT5 not initialized')
            return

        if timeframes is None:
            timeframes = ['1m', '5m', '15m', '1H']

        self.running = True

        threads = []

        # Tick threads
        for sym in self.symbols:

            t = threading.Thread(
                target=self._tick_loop,
                args=(sym,),
                daemon=True
            )

            t.start()
            threads.append(t)

        # Candle threads
        for sym in self.symbols:
            for tf in timeframes:

                t = threading.Thread(
                    target=self._live_loop,
                    args=(sym, tf, interval),
                    daemon=True
                )

                t.start()
                threads.append(t)

        logger.info('[OK] Collector started')

        try:
            for t in threads:
                t.join()

        except KeyboardInterrupt:
            self.stop()

# ================= STOP =================

    def stop(self):

        self.running = False

        mt5.shutdown()

        if self.db_pool:
            self.db_pool.closeall()

        logger.info('Collector stopped')

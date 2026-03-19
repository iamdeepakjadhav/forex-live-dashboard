import psycopg2
from psycopg2 import extras
import pandas as pd

class DBStorage:

    def __init__(self, host="localhost", user="postgres", password="root", database="forex_data"):
        self.host = host
        self.user = user
        self.password = password
        self.database = database

        self.conn = None
        self.cursor = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            self.cursor = self.conn.cursor()
            return True

        except psycopg2.Error as err:
            print(f"PostgreSQL connection error: {err}")
            return False

    def close(self):
        if self.conn:
            self.conn.commit()
            self.cursor.close()
            self.conn.close()

    def insert_candles_batch(self, symbol, timeframe, df):
        if df is None or df.empty:
            return 0

        # candles_data: partitioned table with time_epoch column
        sql = """
        INSERT INTO candles_data
        (symbol, timeframe, datetime, time_epoch, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (symbol, timeframe, datetime) DO NOTHING
        """

        df_reset = df.reset_index()

        values = [
            (
                symbol,
                timeframe,
                row.datetime,
                int(pd.Timestamp(row.datetime).timestamp()),
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
                float(row.volume)
            )
            for row in df_reset.itertuples()
        ]

        try:
            # execute_values is much faster for batch inserts in psycopg2
            extras.execute_values(self.cursor, sql, values)
            self.conn.commit()
            return len(values)

        except psycopg2.Error as err:
            print(f"PostgreSQL insert error: {err}")
            self.conn.rollback()
            return 0

    def get_latest_timestamp(self, symbol):
        sql = """
        SELECT MAX(datetime)
        FROM candles_data
        WHERE symbol=%s
        """
        try:
            self.cursor.execute(sql, (symbol,))
            result = self.cursor.fetchone()
            if result and result[0]:
                return result[0]
            return None

        except psycopg2.Error as err:
            print(f"PostgreSQL read error: {err}")
            return None

    def get_existing_hours(self, symbol, start_date, end_date):
        sql = """
        SELECT datetime
        FROM candles_data
        WHERE symbol=%s AND timeframe='1H' AND datetime >= %s AND datetime <= %s
        """
        try:
            self.cursor.execute(sql, (symbol, start_date, end_date))
            result = self.cursor.fetchall()
            return set(row[0] for row in result)
        except psycopg2.Error as err:
            print(f"PostgreSQL read error: {err}")
            return set()

import lzma
import numpy as np
import pandas as pd


class DukascopyParser:

    def __init__(self, symbol):

        self.symbol = symbol

        self.point_val = 1000.0 if "JPY" in symbol else 100000.0

        self.dtype = np.dtype([
            ("ms", ">u4"),
            ("ask", ">i4"),
            ("bid", ">i4"),
            ("ask_vol", ">f4"),
            ("bid_vol", ">f4")
        ])

    def parse_bi5_content(self, content, dt):

        if not content:
            return None
        
        # Dukascopy sometimes returns 200 OK but the content is actually an HTML error page
        if b"<!DOCTYPE" in content or b"<html" in content.lower():
            return None

        try:
            data = lzma.decompress(content)
        except Exception:
            return None

        if not data:
            return None

        valid_len = len(data) - (len(data) % 20)

        if valid_len == 0:
            return None

        if valid_len != len(data):
            data = data[:valid_len]

        arr = np.frombuffer(data, dtype=self.dtype)

        if arr.size == 0:
            return None

        base_time = np.datetime64(dt)

        timestamps = base_time + arr["ms"].astype("timedelta64[ms]")

        # Convert to native byte order to avoid pandas ValueError on big-endian buffers
        ask = arr["ask"].astype(np.float64) / self.point_val
        bid = arr["bid"].astype(np.float64) / self.point_val
        ask_vol = arr["ask_vol"].astype(np.float64)
        bid_vol = arr["bid_vol"].astype(np.float64)

        df = pd.DataFrame({
            "datetime": timestamps,
            "ask": ask,
            "bid": bid,
            "ask_vol": ask_vol,
            "bid_vol": bid_vol,
        })

        return df


def parse_batch(symbol, batch):
    """
    Parse a batch of downloaded hours using the DukascopyParser.
    batch: list of (dt, content)
    Returns: list of pandas DataFrames
    """
    parser = DukascopyParser(symbol)
    dfs = []
    for dt, content in batch:
        try:
            df = parser.parse_bi5_content(content, dt)
            if df is not None and not df.empty:
                dfs.append(df)
        except Exception as e:
            print(f"Error parsing {dt}: {e}")
    return dfs

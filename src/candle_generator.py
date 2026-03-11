import pandas as pd


class CandleGenerator:

    def __init__(self):

        self.timeframes = {
            "1m": "1min",
            "5m": "5min",
            "10m": "10min",
            "15m": "15min",
            "30m": "30min",
            "1H": "1h",
            "1D": "1D"
        }

    def generate_candles(self, df: pd.DataFrame):

        if df is None or df.empty:
            return {}

        if "datetime" in df.columns:
            df = df.set_index("datetime")

        # mid price
        price = (df["bid"] + df["ask"]) / 2

        # total volume
        vol = df["bid_vol"] + df["ask_vol"]

        temp = pd.DataFrame({
            "price": price,
            "volume": vol
        })

        results = {}

        for name, tf in self.timeframes.items():

            try:

                ohlc = temp["price"].resample(tf).ohlc()

                volume = temp["volume"].resample(tf).sum()

                candles = ohlc.join(volume)

                candles.columns = ["open", "high", "low", "close", "volume"]

                candles = candles.dropna()

                results[name] = candles

            except Exception as e:

                print(f"Resample error {name}: {e}")

        return results
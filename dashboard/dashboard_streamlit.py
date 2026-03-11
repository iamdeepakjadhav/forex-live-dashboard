import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time

st.set_page_config(page_title="Forex Live Dashboard", layout="wide")

API_URL = "http://localhost:5000"

# ---------------- SIDEBAR ----------------

st.sidebar.title("Forex Dashboard")

try:
    symbols = requests.get(f"{API_URL}/api/symbols").json()
except:
    symbols = ["EURUSD.x"]

symbol = st.sidebar.selectbox("Pair", symbols)

try:
    timeframes = requests.get(f"{API_URL}/api/timeframes").json()
except:
    timeframes = ["1m","5m","15m","1H"]

timeframe = st.sidebar.selectbox("Timeframe", timeframes)

# ---------------- HEADER ----------------

st.title(f"{symbol} - {timeframe}")

col1,col2,col3,col4,col5 = st.columns(5)

metric_open = col1.empty()
metric_high = col2.empty()
metric_low = col3.empty()
metric_close = col4.empty()
metric_live = col5.empty()

chart_placeholder = st.empty()

# ---------------- API ----------------

def get_chart():

    try:
        r = requests.get(
            f"{API_URL}/api/data",
            params={"symbol":symbol,"timeframe":timeframe,"limit":300},
            timeout=3
        )

        if r.status_code == 200:
            return r.json()

    except:
        pass

    return []


def get_tick():

    try:
        r = requests.get(
            f"{API_URL}/api/tick",
            params={"symbol":symbol},
            timeout=2
        )

        if r.status_code == 200:
            return r.json()

    except:
        pass

    return None


# ---------------- INITIAL LOAD ----------------

data = get_chart()

df = pd.DataFrame(data)

if not df.empty:
    df["time"] = pd.to_datetime(df["time"],unit="s")


# ---------------- LIVE LOOP ----------------

while True:

    tick = get_tick()

    if tick:

        metric_live.metric(
            "Live",
            f"{tick['last']:.5f}",
            f"Bid {tick['bid']:.5f} Ask {tick['ask']:.5f}"
        )

    data = get_chart()

    if data:

        df = pd.DataFrame(data)
        df["time"] = pd.to_datetime(df["time"],unit="s")

        last = df.iloc[-1]

        metric_open.metric("Open",f"{last['open']:.5f}")
        metric_high.metric("High",f"{last['high']:.5f}")
        metric_low.metric("Low",f"{last['low']:.5f}")
        metric_close.metric("Close",f"{last['close']:.5f}")

        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"]
        ))

        fig.update_layout(
            template="plotly_dark",
            height=600,
            xaxis_rangeslider_visible=False
        )

        chart_placeholder.plotly_chart(
            fig,
            use_container_width=True,
            key=str(time.time())
        )

    time.sleep(0.5)
import requests
import json
import datetime
import math

try:
    print("Testing /api/data")
    res = requests.get('http://127.0.0.1:5000/api/data?symbol=EURUSD.x&timeframe=1H&limit=3')
    data = res.json()
    print("DATA", data)
    
    print("\nTesting /api/ticks")
    res2 = requests.get('http://127.0.0.1:5000/api/ticks')
    ticks = res2.json()
    print("TICKS", ticks)

    print("\nTesting /api/ticks/live")
    res3 = requests.get('http://127.0.0.1:5000/api/ticks/live')
    live = res3.json()
    print("LIVE", live)
    
except Exception as e:
    print("Error", e)

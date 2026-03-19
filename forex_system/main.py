import time
from datetime import datetime, timedelta, timezone
import concurrent.futures
import pandas as pd
import os
import multiprocessing
import asyncio
import sys

from src.async_downloader import AsyncDukascopyDownloader
from src.parser import DukascopyParser, parse_batch
from src.candle_generator import CandleGenerator
from src.db_storage import DBStorage

# SYMBOLS = [
#     "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
#     "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"
# ]

SYMBOLS = [
    "GBPJPY"
]

MAX_WORKERS = multiprocessing.cpu_count()  # Using all cores for maximum speed


def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def process_chunks(symbol, start_date, end_date, db, generator):
    downloader = AsyncDukascopyDownloader(data_dir="data", max_concurrent=50)
    
    db_symbol = f"{symbol}.x"
    existing_hours = db.get_existing_hours(db_symbol, start_date, end_date)
    print(f"[{symbol}] Found {len(existing_hours)} existing hours in DB for {db_symbol}")

    current_dt = start_date
    print(f"[{symbol}] Start from {current_dt}")

    while current_dt <= end_date:
        # Process in larger chunks (3 months at a time) to reduce DB insert frequency overhead
        if current_dt.month <= 9:
            next_chunk_start = datetime(current_dt.year, current_dt.month + 3, 1)
        else:
            next_chunk_start = datetime(current_dt.year + 1, (current_dt.month + 3) % 12 or 12, 1)
            
        chunk_end = min(next_chunk_start - timedelta(hours=1), end_date)
        print(f"\n[{symbol}] Processing Chunk {current_dt.strftime('%Y-%m-%d')} -> {chunk_end.strftime('%Y-%m-%d')}")
        
        chunk_start_time = time.time()
        hours_to_dl = []
        t = current_dt

        while t <= chunk_end:
            if t not in existing_hours and t.weekday() != 5:
                hours_to_dl.append(t)
            t += timedelta(hours=1)

        if not hours_to_dl:
            print(f"[{symbol}] No new hours for this chunk.")
            current_dt = chunk_end + timedelta(hours=1)
            continue

        print(f"[{symbol}] Downloading {len(hours_to_dl)} hours...")
        dl_start = time.time()
        downloaded_data = await downloader.download_batch(symbol, hours_to_dl)
        print(f"[{symbol}] Downloaded {len(downloaded_data)} valid hours in {time.time() - dl_start:.2f}s")
        
        if downloaded_data:
            print(f"[{symbol}] Parsing data across {MAX_WORKERS} cores...")
            parse_start = time.time()
            
            chunk_size = max(1, len(downloaded_data) // (MAX_WORKERS * 2))
            batches = list(chunk_list(downloaded_data, chunk_size))
            
            tick_dfs = []
            with concurrent.futures.ProcessPoolExecutor(MAX_WORKERS) as executor:
                futures = [executor.submit(parse_batch, symbol, b) for b in batches]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    tick_dfs.extend(result)
            
            print(f"[{symbol}] Parsed in {time.time() - parse_start:.2f}s")
            
            if tick_dfs:
                print(f"[{symbol}] Generating candles and saving to DB...")
                combined = pd.concat(tick_dfs)
                candles = generator.generate_candles(combined)
                total_inserted = 0
                for timeframe, df in candles.items():
                    inserted = db.insert_candles_batch(db_symbol, timeframe, df)
                    total_inserted += inserted
                
                print(f"[{symbol}] Inserted {total_inserted} total candles")
                
                del combined
                del candles
            else:
                print(f"[{symbol}] No valid tick data after parsing.")
            
            del tick_dfs
            del downloaded_data

        print(f"[{symbol}] Chunk done in {time.time() - chunk_start_time:.2f}s")
        current_dt = chunk_end + timedelta(hours=1)


def run_pipeline(start_date: datetime, end_date: datetime):
    print("=== Starting Async Forex Data Pipeline ===")
    print(f"Range: {start_date} -> {end_date}")

    generator = CandleGenerator()
    db = DBStorage()

    if not db.connect():
        print("DB connection failed")
        return

    for symbol in SYMBOLS:
        print(f"\n--- Processing {symbol} ---")
        asyncio.run(process_chunks(symbol, start_date, end_date, db, generator))

    db.close()
    print("\n=== PIPELINE COMPLETE ===")


if __name__ == "__main__":
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    start_date = datetime(2010, 1, 1)
    end_date = now - timedelta(hours=1)

    run_pipeline(start_date, end_date)
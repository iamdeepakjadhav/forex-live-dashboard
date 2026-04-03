"""
Data Filler - Downloads and fills missing hours in database
Uses async downloading + multiprocessing parsing for speed
"""

import asyncio
import time
import pandas as pd
import concurrent.futures
import multiprocessing
from datetime import datetime
from typing import List

from src.async_downloader import AsyncDukascopyDownloader
from src.parser import parse_batch
from src.candle_generator import CandleGenerator
from src.db_storage import DBStorage


class DataFiller:
    """
    Fills missing hours in candles_data table
    - Downloads from Dukascopy
    - Parses ticks efficiently
    - Generates candles for all timeframes
    - Inserts with conflict handling
    """

    def __init__(self, max_workers=None, max_concurrent=50):
        self.max_workers = max_workers or multiprocessing.cpu_count()
        self.max_concurrent = max_concurrent
        self.downloader = None
        self.generator = CandleGenerator()
        self.db = DBStorage()
        self.download_count = 0

    def chunk_list(self, lst, n):
        """Split list into chunks"""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    async def download_missing_hours(self, symbol: str, missing_hours: List[datetime]) -> dict:
        """
        Async download missing hours
        Returns: {hour: tick_data} dict
        """
        self.downloader = AsyncDukascopyDownloader(data_dir="data", max_concurrent=self.max_concurrent)
        
        print(f"   ⬇️  Downloading {len(missing_hours)} hours for {symbol}...")
        
        start_time = time.time()
        downloaded_data = await self.downloader.download_batch(symbol, missing_hours)
        elapsed = time.time() - start_time
        
        print(f"   ✅ Downloaded {len(downloaded_data)} valid hours in {elapsed:.2f}s")
        
        return downloaded_data

    def parse_downloaded_data(self, symbol: str, downloaded_data: dict) -> List[pd.DataFrame]:
        """
        Parse downloaded tick data using multiprocessing
        Returns: List of DataFrames with parsed ticks
        """
        if not downloaded_data:
            return []
        
        print(f"   🔄 Parsing {len(downloaded_data)} hours with {self.max_workers} cores...")
        
        # Convert to list of (hour, data) tuples
        data_list = list(downloaded_data.items())
        
        # Chunk for parallel processing
        chunk_size = max(1, len(data_list) // (self.max_workers * 2))
        batches = list(self.chunk_list(data_list, chunk_size))
        
        parse_start = time.time()
        tick_dfs = []
        
        with concurrent.futures.ProcessPoolExecutor(self.max_workers) as executor:
            futures = [executor.submit(self._parse_batch_wrapper, symbol, batch) for batch in batches]
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    tick_dfs.extend(result)
                except Exception as e:
                    print(f"   ❌ Parse error: {e}")
        
        elapsed = time.time() - parse_start
        print(f"   ✅ Parsed in {elapsed:.2f}s")
        
        return tick_dfs

    def _parse_batch_wrapper(self, symbol: str, batch: list) -> List[pd.DataFrame]:
        """Wrapper for parsing batches in multiprocessing context"""
        from src.parser import DukascopyParser
        
        parser = DukascopyParser()
        tick_dfs = []
        
        for hour, data in batch:
            try:
                ticks = parser.parse(data)
                if ticks is not None and not ticks.empty:
                    tick_dfs.append(ticks)
            except Exception as e:
                print(f"   ⚠️  Parse error for {hour}: {e}")
        
        return tick_dfs

    def generate_and_store_candles(self, symbol: str, tick_dfs: List[pd.DataFrame]) -> dict:
        """
        Generate candles from ticks and store to database
        Returns: Statistics dict
        """
        if not tick_dfs:
            print(f"   ⚠️  No parsed data to store for {symbol}")
            return {"inserted": 0, "timeframes": {}}
        
        print(f"   📊 Generating candles from {len(tick_dfs)} hours...")
        
        # Combine all ticks
        combined = pd.concat(tick_dfs, ignore_index=True)
        print(f"   📈 Total ticks: {len(combined)}")
        
        # Generate candles for all timeframes
        candles = self.generator.generate_candles(combined)
        
        if not candles:
            print(f"   ⚠️  No candles generated for {symbol}")
            return {"inserted": 0, "timeframes": {}}
        
        # Store to database
        print(f"   💾 Storing candles to database...")
        
        if not self.db.connect():
            print(f"   ❌ Failed to connect to database")
            return {"inserted": 0, "timeframes": {}}
        
        stats = {"inserted": 0, "timeframes": {}}
        
        for timeframe, df in candles.items():
            if df is not None and not df.empty:
                inserted = self.db.insert_candles_batch(symbol, timeframe, df)
                stats["timeframes"][timeframe] = inserted
                stats["inserted"] += inserted
                if inserted > 0:
                    print(f"      ✅ {timeframe}: {inserted} candles")
        
        self.db.close()
        
        return stats

    async def fill_missing_hours(self, symbol: str, missing_hours: List[datetime]) -> dict:
        """
        Complete fill process: download -> parse -> generate -> store
        Returns: Result statistics
        """
        if not missing_hours:
            return {"symbol": symbol, "status": "no_missing_hours", "inserted": 0}
        
        print(f"\n🚀 Processing {symbol} ({len(missing_hours)} hours)")
        
        try:
            # Download
            downloaded_data = await self.download_missing_hours(symbol, missing_hours)
            
            if not downloaded_data:
                print(f"   ❌ No data downloaded for {symbol}")
                return {"symbol": symbol, "status": "download_failed", "inserted": 0}
            
            # Parse
            tick_dfs = self.parse_downloaded_data(symbol, downloaded_data)
            
            if not tick_dfs:
                print(f"   ❌ No ticks parsed for {symbol}")
                return {"symbol": symbol, "status": "parse_failed", "inserted": 0}
            
            # Generate and store
            stats = self.generate_and_store_candles(symbol, tick_dfs)
            
            return {
                "symbol": symbol,
                "status": "success",
                "missing_hours": len(missing_hours),
                "downloaded": len(downloaded_data),
                "parsed_hours": len(tick_dfs),
                "inserted": stats["inserted"],
                "timeframes": stats["timeframes"]
            }
        
        except Exception as e:
            print(f"   ❌ Error processing {symbol}: {e}")
            return {"symbol": symbol, "status": "error", "error": str(e), "inserted": 0}

    async def fill_multiple_symbols(self, symbol_hours: dict) -> list:
        """
        Fill multiple symbols in parallel
        symbol_hours: {symbol: [missing_hours_list]}
        Returns: List of result dicts
        """
        tasks = [
            self.fill_missing_hours(symbol, hours)
            for symbol, hours in symbol_hours.items()
        ]
        
        results = await asyncio.gather(*tasks)
        return results

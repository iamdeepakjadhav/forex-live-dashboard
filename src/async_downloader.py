import aiohttp
import asyncio
import os
import random

class AsyncDukascopyDownloader:
    BASE_URL = "https://datafeed.dukascopy.com/datafeed"

    def __init__(self, data_dir="data", max_concurrent=50):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.max_concurrent = max_concurrent
        self.download_count = 0
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ]

    def build_url(self, symbol, dt):
        month = dt.month - 1
        return (
            f"{self.BASE_URL}/{symbol}/"
            f"{dt.year}/{month:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"
        )

    async def _download_hour(self, session, symbol, dt, semaphore):
        url = self.build_url(symbol, dt)
        retries = 3

        headers = {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        }

        for attempt in range(retries):
            try:
                async with semaphore:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15, connect=5)) as response:
                        if response.status == 200:
                            data = await response.read()
                            
                            # Filter empty files or error HTMLs returned by Dukascopy
                            if not data or len(data) < 20: 
                                return (dt, None)
                            
                            self.download_count += 1
                            if self.download_count % 100 == 0:
                                print(f"[{symbol}] Downloaded {self.download_count} hours...")

                            return (dt, data)
                        elif response.status == 404:
                            # 404 means no data for this specific hour (e.g. weekend/holiday)
                            return (dt, None)
                        elif response.status in (403, 429, 503):
                            # Rate limits or blocks - back off
                            await asyncio.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
                        else:
                            await asyncio.sleep((1 ** attempt) + random.uniform(0.1, 0.5))
            except Exception:
                await asyncio.sleep((2 ** attempt) + random.uniform(0.5, 1.0))

        return (dt, None)

    async def download_batch(self, symbol, datetimes):
        self.download_count = 0
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Proper connection pooling is critical for speed and avoiding server tar-pitting
        connector = aiohttp.TCPConnector(limit=self.max_concurrent, keepalive_timeout=60)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self._download_hour(session, symbol, dt, semaphore) for dt in datetimes]
            results = await asyncio.gather(*tasks)
            return [(dt, data) for dt, data in results if data is not None]

import requests
import os
import time


class DukascopyDownloader:

    BASE_URL = "https://datafeed.dukascopy.com/datafeed"

    def __init__(self, data_dir="data"):

        self.data_dir = data_dir

        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # Persistent HTTP session
        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0"
        })

        self.download_count = 0

    def build_url(self, symbol, dt):

        month = dt.month - 1

        return (
            f"{self.BASE_URL}/{symbol}/"
            f"{dt.year}/{month:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"
        )

    def download_hour(self, symbol, dt):

        url = self.build_url(symbol, dt)

        retries = 5

        for attempt in range(retries):

            try:

                response = self.session.get(url, timeout=20)

                if response.status_code == 200:

                    data = response.content

                    if not data:
                        return None

                    self.download_count += 1

                    if self.download_count % 50 == 0:
                        print(
                            f"[{symbol}] downloaded {self.download_count} hours"
                        )

                    return data

                elif response.status_code == 404:

                    return None

                elif response.status_code in (429, 503):

                    wait = 2 ** attempt
                    time.sleep(wait)

                else:

                    if attempt == retries - 1:
                        print(
                            f"[{symbol}] HTTP {response.status_code} {dt}"
                        )

                    time.sleep(1)

            except requests.exceptions.RequestException as e:

                if attempt == retries - 1:
                    print(f"[{symbol}] request error {dt} {e}")

                time.sleep(2 ** attempt)

        return None
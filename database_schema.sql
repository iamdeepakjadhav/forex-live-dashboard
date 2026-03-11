CREATE TABLE IF NOT EXISTS candles (
    symbol VARCHAR(10) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    datetime TIMESTAMP NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (symbol, timeframe, datetime)
);

CREATE INDEX IF NOT EXISTS idx_symbol_timeframe_datetime 
ON candles(symbol, timeframe, datetime);
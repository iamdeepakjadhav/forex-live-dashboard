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



CREATE TABLE IF NOT EXISTS ticks (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    tick_time TIMESTAMP NOT NULL,
    bid DOUBLE PRECISION NOT NULL,
    ask DOUBLE PRECISION NOT NULL,
    mid DOUBLE PRECISION NOT NULL,
    spread DOUBLE PRECISION NOT NULL
);

CREATE INDEX idx_ticks_symbol_time 
ON ticks(symbol, tick_time DESC);













-- ==============================================================================
-- 1. MAIN TABLE BANANA (candles_data)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.candles_data (
    symbol VARCHAR(10) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    datetime TIMESTAMP NOT NULL,
    time_epoch BIGINT NOT NULL, -- Fast query ke liye
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    
    -- Partition Key (timeframe) ko Primary Key me rakhna zaroori hai
    PRIMARY KEY (symbol, timeframe, datetime)
) PARTITION BY LIST (timeframe);


-- ==============================================================================
-- 2. PARTITIONS BANANA 
-- (Tumhare 8 timeframes + MT5 ke saare future timeframes)
-- IF NOT EXISTS lagaya hai taaki already bani hui table par error na aaye
-- ==============================================================================

-- -> Tumhare current timeframes (Screenshot ke hisaab se)
CREATE TABLE IF NOT EXISTS candles_data_1m  PARTITION OF public.candles_data FOR VALUES IN ('1m');
CREATE TABLE IF NOT EXISTS candles_data_5m  PARTITION OF public.candles_data FOR VALUES IN ('5m');
CREATE TABLE IF NOT EXISTS candles_data_10m PARTITION OF public.candles_data FOR VALUES IN ('10m');
CREATE TABLE IF NOT EXISTS candles_data_15m PARTITION OF public.candles_data FOR VALUES IN ('15m');
CREATE TABLE IF NOT EXISTS candles_data_30m PARTITION OF public.candles_data FOR VALUES IN ('30m');
CREATE TABLE IF NOT EXISTS candles_data_1H  PARTITION OF public.candles_data FOR VALUES IN ('1H');
CREATE TABLE IF NOT EXISTS candles_data_4H  PARTITION OF public.candles_data FOR VALUES IN ('4H');
CREATE TABLE IF NOT EXISTS candles_data_1D  PARTITION OF public.candles_data FOR VALUES IN ('1D');

-- -> Future safety ke liye baaki MT5 timeframes
CREATE TABLE IF NOT EXISTS candles_data_2m  PARTITION OF public.candles_data FOR VALUES IN ('2m');
CREATE TABLE IF NOT EXISTS candles_data_3m  PARTITION OF public.candles_data FOR VALUES IN ('3m');
CREATE TABLE IF NOT EXISTS candles_data_4m  PARTITION OF public.candles_data FOR VALUES IN ('4m');
CREATE TABLE IF NOT EXISTS candles_data_6m  PARTITION OF public.candles_data FOR VALUES IN ('6m');
CREATE TABLE IF NOT EXISTS candles_data_12m PARTITION OF public.candles_data FOR VALUES IN ('12m');
CREATE TABLE IF NOT EXISTS candles_data_20m PARTITION OF public.candles_data FOR VALUES IN ('20m');
CREATE TABLE IF NOT EXISTS candles_data_2H  PARTITION OF public.candles_data FOR VALUES IN ('2H');
CREATE TABLE IF NOT EXISTS candles_data_3H  PARTITION OF public.candles_data FOR VALUES IN ('3H');
CREATE TABLE IF NOT EXISTS candles_data_6H  PARTITION OF public.candles_data FOR VALUES IN ('6H');
CREATE TABLE IF NOT EXISTS candles_data_8H  PARTITION OF public.candles_data FOR VALUES IN ('8H');
CREATE TABLE IF NOT EXISTS candles_data_12H PARTITION OF public.candles_data FOR VALUES IN ('12H');
CREATE TABLE IF NOT EXISTS candles_data_1W  PARTITION OF public.candles_data FOR VALUES IN ('1W');
CREATE TABLE IF NOT EXISTS candles_data_1M  PARTITION OF public.candles_data FOR VALUES IN ('1M');

-- -> Agar galti se koi ajeeb timeframe aaya, toh yahan jayega (error se bachne ke liye)
CREATE TABLE IF NOT EXISTS candles_data_default PARTITION OF public.candles_data DEFAULT;


-- ==============================================================================
-- 3. FAST INDEX LAGANA
-- ==============================================================================
CREATE INDEX IF NOT EXISTS idx_candles_data_fast ON public.candles_data (symbol, timeframe, datetime DESC);


-- ==============================================================================
-- 4. DATA TRANSFER (MIGRATION)
-- ==============================================================================
-- NOTE: 1.25 Crore rows copy hone me pgAdmin thoda time lega (approx 2 se 6 minute). 
-- Isko pura chalne dena.
-- ON CONFLICT lagaya hai taaki agar koi row pehle se copy ho chuki hai toh duplicate error na aaye.

INSERT INTO public.candles_data (symbol, timeframe, datetime, time_epoch, open, high, low, close, volume)
SELECT 
    symbol, 
    timeframe, 
    datetime, 
    CAST(EXTRACT(EPOCH FROM datetime) AS bigint) AS time_epoch,
    open, 
    high, 
    low, 
    close, 
    volume
FROM public.candles
ON CONFLICT (symbol, timeframe, datetime) DO NOTHING;
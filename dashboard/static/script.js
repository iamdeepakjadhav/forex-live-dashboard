/**
 * ╔════════════════════════════════════════════════════════════════════════╗
 * ║          Forex Live Dashboard – Line + Candlestick Chart              ║
 * ║  ✅ LIVE Price Line (Right side updates every 1 second)               ║
 * ║  ✅ Candlestick Chart (Background)                                    ║
 * ║  ✅ Real-time price label animation                                   ║
 * ║  ✅ Green/Red based on price direction                                ║
 * ╚════════════════════════════════════════════════════════════════════════╝
 */

(async function () {
    'use strict';

    // ═══════════════════════════════════════════════════════════════════════
    // TIMEZONE
    // ═══════════════════════════════════════════════════════════════════════

    const TZ_OFFSET = -(new Date().getTimezoneOffset() * 60);

    function toLocalTime(utcEpoch) {
        return utcEpoch + TZ_OFFSET;
    }

    function toUtcTime(localEpoch) {
        return localEpoch - TZ_OFFSET;
    }

    // ══════��════════════════════════════════════════════════════════════════
    // DOM REFS
    // ══���════════════════════════════════════════════════════════════════════

    const chartContainer = document.getElementById('tvchart');
    const symbolSelect = document.getElementById('symbol-select');
    const chartTitle = document.getElementById('chart-title');
    const loadingOverlay = document.getElementById('loading-overlay');
    const timeframeGroup = document.getElementById('timeframe-buttons');

    const statO = document.getElementById('stat-o');
    const statH = document.getElementById('stat-h');
    const statL = document.getElementById('stat-l');
    const statC = document.getElementById('stat-c');

    let liveBadge = document.getElementById('live-price-badge');
    if (!liveBadge) {
        liveBadge = document.createElement('span');
        liveBadge.id = 'live-price-badge';
        liveBadge.style.cssText =
            'margin-left:14px;padding:6px 14px;border-radius:8px;' +
            'background:#64748b;color:#fff;font-size:0.95em;font-weight:700;' +
            'transition:background 0.3s ease;user-select:none;';
        const titleEl = document.getElementById('chart-title');
        if (titleEl && titleEl.parentNode) {
            titleEl.parentNode.insertBefore(liveBadge, titleEl.nextSibling);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════

    let currentSymbol = 'EURUSD.x';
    let currentTimeframe = '1H';
    let chart = null;
    let candleSeries = null;
    let lineSeries = null;         // ✅ PRICE LINE SERIES
    let tickInterval = null;
    let latestInterval = null;
    let lastCandleSnap = null;

    let apiErrorCount = 0;
    let maxApiErrors = 5;
    let isChartReady = false;

    // ═══════════════════════════════════════════════════════════════════════
    // CHART INIT
    // ═══════════════════════════════════════════════════════════════════════

    function initChart() {
        if (!chartContainer) {
            console.error('[FAILED] Chart container not found');
            return;
        }

        const rect = chartContainer.getBoundingClientRect();
        const width = rect.width > 0 ? rect.width : 1000;
        const height = rect.height > 0 ? rect.height : 600;

        try {
            chart = LightweightCharts.createChart(chartContainer, {
                width: width,
                height: height,
                layout: {
                    textColor: '#d1d5db',
                    backgroundColor: 'transparent',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
                },
                grid: {
                    vertLines: {
                        color: 'rgba(51, 65, 85, 0.35)',
                        style: LightweightCharts.LineStyle.SparseDotted,
                    },
                    horzLines: {
                        color: 'rgba(51, 65, 85, 0.35)',
                        style: LightweightCharts.LineStyle.SparseDotted,
                    },
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {
                        width: 1,
                        color: 'rgba(148, 163, 184, 0.5)',
                        style: LightweightCharts.LineStyle.SparseDotted,
                    },
                    horzLine: {
                        width: 1,
                        color: 'rgba(148, 163, 184, 0.5)',
                        style: LightweightCharts.LineStyle.SparseDotted,
                        labelVisible: true,
                    },
                },
                rightPriceScale: {
                    borderColor: 'rgba(51, 65, 85, 0.8)',
                    autoScale: true,
                    scaleMargins: { top: 0.1, bottom: 0.1 },
                    entireTextOnly: false,
                    textColor: '#9ca3af',
                },
                timeScale: {
                    borderColor: 'rgba(51, 65, 85, 0.8)',
                    timeVisible: true,
                    secondsVisible: false,
                    rightOffset: 5,
                    barSpacing: 8,
                    tickMarkFormatter: (time) => {
                        const d = new Date(time * 1000);
                        return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
                    },
                },
            });

            console.log(`[OK] Chart initialized (${width}×${height})`);

            // ── 1️⃣ CANDLESTICK SERIES (Background) ────────────────────────
            candleSeries = chart.addCandlestickSeries({
                upColor: '#10b981',
                downColor: '#ef4444',
                borderVisible: false,
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
                priceFormat: {
                    type: 'price',
                    precision: 5,
                    minMove: 0.00001,
                },
                lastValueVisible: false,   // ✅ DISABLE candlestick price line
                priceLineVisible: false,   // ✅ DISABLE candlestick price line
            });

            // ── 2️⃣ LINE SERIES (Price tracking) ──────────────────────────
            /**
             * ✅ Line series - shows continuous price line with label on right
             * This is what moves up/down with every tick
             */
            lineSeries = chart.addLineSeries({
                color: '#10b981',              // Default green
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                priceLineVisible: true,        // ✅ SHOW price line
                priceLineColor: '#10b981',
                priceLineWidth: 2,
                priceLineStyle: LightweightCharts.LineStyle.Dashed,
                lastValueVisible: true,        // ✅ SHOW price label on right
                title: 'Live Price',
            });

            // ── RESIZE OBSERVER ───────────────────────────────────────
            const resizeObserver = new ResizeObserver(entries => {
                if (!entries || !entries[0]) return;
                const { width, height } = entries[0].contentRect;
                if (width > 0 && height > 0) {
                    chart.applyOptions({ width, height });
                }
            });
            resizeObserver.observe(chartContainer);

            // ── CROSSHAIR ─────────────────────────────────────────────
            chart.subscribeCrosshairMove(param => {
                if (!param || !param.time) {
                    if (lastCandleSnap) {
                        updateOHLC(lastCandleSnap.open, lastCandleSnap.high, lastCandleSnap.low, lastCandleSnap.close);
                    }
                    return;
                }

                if (param.seriesData && param.seriesData.size > 0) {
                    const candle = param.seriesData.get(candleSeries);
                    if (candle) {
                        updateOHLC(candle.open, candle.high, candle.low, candle.close);
                    }
                }
            });

            isChartReady = true;
            return true;

        } catch (e) {
            console.error('[FAILED] Chart init:', e);
            return false;
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // UPDATE LINE SERIES COLOR (Green/Red)
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * ✅ Change line color based on price direction
     */
    function updateLineColor(open, close) {
        if (!lineSeries) return;

        const isUp = close >= open;
        const lineColor = isUp ? '#10b981' : '#ef4444';

        try {
            lineSeries.applyOptions({
                color: lineColor,
                priceLineColor: lineColor,
            });
        } catch (e) {
            console.debug('[DEBUG] Line color update: ' + e.message);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // UPDATE OHLC
    // ═══════════════════════════════════════════════════════════════════════

    function updateOHLC(open, high, low, close) {
        const fmt = v => (typeof v === 'number' ? v.toFixed(5) : '---');

        statO.textContent = fmt(open);
        statH.textContent = fmt(high);
        statL.textContent = fmt(low);
        statC.textContent = fmt(close);

        if (typeof close === 'number' && typeof open === 'number') {
            statC.style.color = (close >= open) ? '#10b981' : '#ef4444';
        }

        // ✅ Update line color
        updateLineColor(open, close);
    }

    function showLoading(visible) {
        if (loadingOverlay) {
            loadingOverlay.classList.toggle('hidden', !visible);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // API CALLS
    // ═══════════════════════════════════════════════════════════════════════

    async function loadSymbols() {
        try {
            const res = await fetch('/api/symbols');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const symbols = await res.json();

            if (symbols && Array.isArray(symbols) && symbols.length > 0) {
                symbolSelect.innerHTML = '';
                symbols.forEach(sym => {
                    const opt = document.createElement('option');
                    opt.value = opt.textContent = sym;
                    symbolSelect.appendChild(opt);
                });
                currentSymbol = symbols[0];
                symbolSelect.value = currentSymbol;
                console.log(`[OK] ${symbols.length} symbols loaded`);
            }
        } catch (e) {
            console.error('[FAILED] loadSymbols:', e);
        }
    }

    async function loadTimeframes() {
        try {
            const res = await fetch('/api/timeframes');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            let timeframes = await res.json() || ['1m', '5m', '15m', '30m', '1H', '4H', '1D'];

            timeframeGroup.innerHTML = '';
            timeframes.forEach(tf => {
                const btn = document.createElement('button');
                btn.className = `tf-btn ${tf === currentTimeframe ? 'active' : ''}`;
                btn.dataset.tf = tf;
                btn.textContent = tf;
                btn.style.cssText = `padding: 6px 12px; margin-right: 5px; border: 1px solid #475569; background: #1e293b; color: #cbd5e1; border-radius: 5px; cursor: pointer; font-weight: 500; transition: all 0.2s;`;

                btn.addEventListener('click', () => {
                    document.querySelectorAll('.tf-btn').forEach(b => {
                        b.classList.remove('active');
                        b.style.background = '#1e293b';
                        b.style.color = '#cbd5e1';
                    });
                    btn.classList.add('active');
                    btn.style.background = '#10b981';
                    btn.style.color = '#fff';
                    currentTimeframe = tf;
                    lastCandleSnap = null;
                    apiErrorCount = 0;
                    fetchAndDraw();
                    restartPolling();
                });

                timeframeGroup.appendChild(btn);
            });

            const firstBtn = timeframeGroup.querySelector('.tf-btn.active');
            if (firstBtn) {
                firstBtn.style.background = '#10b981';
                firstBtn.style.color = '#fff';
            }

            console.log(`[OK] ${timeframes.length} timeframes loaded`);
        } catch (e) {
            console.error('[FAILED] loadTimeframes:', e);
        }
    }

    async function fetchAndDraw() {
        showLoading(true);
        chartTitle.textContent = `${currentSymbol} - ${currentTimeframe}`;
        lastCandleSnap = null;

        try {
            const url = `/api/data?symbol=${encodeURIComponent(currentSymbol)}&timeframe=${encodeURIComponent(currentTimeframe)}&limit=10000`;
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const raw = await res.json();

            if (raw && Array.isArray(raw) && raw.length > 0) {
                const sorted = raw
                    .map(d => ({
                        time: toLocalTime(d.time),
                        open: Number(d.open),
                        high: Number(d.high),
                        low: Number(d.low),
                        close: Number(d.close),
                        volume: Number(d.volume) || 0,
                    }))
                    .sort((a, b) => a.time - b.time);

                const unique = [];
                let lastTime = -1;
                for (const candle of sorted) {
                    if (candle.time > lastTime) {
                        unique.push(candle);
                        lastTime = candle.time;
                    }
                }

                if (candleSeries && isChartReady) {
                    // ✅ Set candlestick data
                    candleSeries.setData(unique);

                    // ✅ Set line series data (close prices)
                    if (lineSeries) {
                        lineSeries.setData(unique.map(c => ({
                            time: c.time,
                            value: c.close,
                        })));
                    }

                    chart.timeScale().fitContent();
                    console.log(`[OK] ${unique.length} candles loaded`);

                    const tail = unique[unique.length - 1];
                    if (tail) {
                        lastCandleSnap = { ...tail };
                        updateOHLC(tail.open, tail.high, tail.low, tail.close);
                    }
                }

                apiErrorCount = 0;

            } else {
                console.warn('[SKIP] No candle data');
            }

        } catch (e) {
            console.error('[FAILED] fetchAndDraw:', e);
            apiErrorCount++;
            if (apiErrorCount >= maxApiErrors) {
                liveBadge.textContent = '[ERROR] API Failures';
                liveBadge.style.background = '#dc2626';
            }
        } finally {
            showLoading(false);
        }
    }

    async function pollLatestCandle() {
        try {
            const url = `/api/latest?symbol=${encodeURIComponent(currentSymbol)}&timeframe=${encodeURIComponent(currentTimeframe)}`;
            const res = await fetch(url);
            if (!res.ok) return;

            const data = await res.json();
            if (data && data.time && candleSeries && isChartReady) {
                const candle = {
                    time: toLocalTime(data.time),
                    open: Number(data.open),
                    high: Number(data.high),
                    low: Number(data.low),
                    close: Number(data.close),
                    volume: Number(data.volume) || 0,
                };

                lastCandleSnap = candle;
                candleSeries.update(candle);

                // ✅ Update line series too
                if (lineSeries) {
                    lineSeries.update({
                        time: candle.time,
                        value: candle.close,
                    });
                }

                updateOHLC(candle.open, candle.high, candle.low, candle.close);
            }

        } catch (e) {
            console.debug('[INFO] pollLatestCandle: ' + e.message);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // TIMEFRAME HELPERS
    // ═══════════════════════════════════════════════════════════════════════

    const TF_SECONDS = {
        '1m': 60, '5m': 300, '10m': 600, '15m': 900, '30m': 1800,
        '1H': 3600, '2H': 7200, '4H': 14400, '8H': 28800, '12H': 43200,
        '1D': 86400, '1W': 604800, '1M': 2592000
    };

    function getBarStart(utcEpoch, tf) {
        const barSizeSeconds = TF_SECONDS[tf] || 3600;
        return Math.floor(utcEpoch / barSizeSeconds) * barSizeSeconds;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // LIVE TICK POLLING
    // ═══════════════════════════════════════════════════════════════════════

    // async function pollLiveTick() {
    //     try {
    //         const url = `/api/tick?symbol=${encodeURIComponent(currentSymbol)}`;
    //         const res = await fetch(url);

    //         if (!res.ok) {
    //             liveBadge.textContent = '[CLOSED] Market Closed';
    //             liveBadge.style.background = '#64748b';
    //             return;
    //         }

    //         const tick = await res.json();
    //         if (!tick || typeof tick.last !== 'number') {
    //             liveBadge.textContent = '[WARNING] No Tick Data';
    //             liveBadge.style.background = '#f59e0b';
    //             return;
    //         }

    //         const price = tick.last;
    //         liveBadge.textContent = `[LIVE] ${price.toFixed(5)}`;
    //         liveBadge.style.background = '#10b981';

    //         if (!candleSeries || !lastCandleSnap || !isChartReady || !lineSeries) {
    //             return;
    //         }

    //         const nowLocal = Math.floor(Date.now() / 1000);
    //         const nowUtc = toUtcTime(nowLocal);
    //         const barStartUtc = getBarStart(nowUtc, currentTimeframe);
    //         const barStartLocal = toLocalTime(barStartUtc);

    //         if (barStartLocal === lastCandleSnap.time) {
    //             // Same bar
    //             const updated = {
    //                 time: lastCandleSnap.time,
    //                 open: lastCandleSnap.open,
    //                 high: Math.max(lastCandleSnap.high, price),
    //                 low: Math.min(lastCandleSnap.low, price),
    //                 close: price,
    //             };
    //             candleSeries.update(updated);

    //             // ✅ Update line series
    //             lineSeries.update({
    //                 time: updated.time,
    //                 value: updated.close,
    //             });

    //             updateOHLC(updated.open, updated.high, updated.low, updated.close);

    //         } else if (barStartLocal > lastCandleSnap.time) {
    //             // New bar
    //             const newCandle = {
    //                 time: barStartLocal,
    //                 open: lastCandleSnap.close,
    //                 high: Math.max(lastCandleSnap.close, price),
    //                 low: Math.min(lastCandleSnap.close, price),
    //                 close: price,
    //             };
    //             candleSeries.update(newCandle);

    //             // ✅ Update line series
    //             lineSeries.update({
    //                 time: newCandle.time,
    //                 value: newCandle.close,
    //             });

    //             lastCandleSnap = newCandle;
    //             updateOHLC(newCandle.open, newCandle.high, newCandle.low, newCandle.close);
    //             console.log(`[NEW CANDLE] ${currentTimeframe}`);
    //         }

    //         apiErrorCount = 0;

    //     } catch (e) {
    //         console.debug('[INFO] pollLiveTick: ' + e.message);
    //         liveBadge.textContent = '[ERROR] MT5 Offline';
    //         liveBadge.style.background = '#ef4444';
    //     }
    // }

    async function pollLiveTick() {
        try {
            const url = `/api/tick?symbol=${encodeURIComponent(currentSymbol)}`;
            const res = await fetch(url);

            if (!res.ok) {
                liveBadge.textContent = '[CLOSED] Market Closed';
                liveBadge.style.background = '#64748b';
                return;
            }

            const tick = await res.json();
            if (!tick || typeof tick.last !== 'number') {
                liveBadge.textContent = '[WARNING] No Tick Data';
                liveBadge.style.background = '#f59e0b';
                return;
            }

            const price = tick.last;
            liveBadge.textContent = `[LIVE] ${price.toFixed(5)}`;
            liveBadge.style.background = '#10b981';

            if (!candleSeries || !lastCandleSnap || !isChartReady || !lineSeries) {
                return;
            }

            const nowLocal = Math.floor(Date.now() / 1000);
            const nowUtc = toUtcTime(nowLocal);
            const barStartUtc = getBarStart(nowUtc, currentTimeframe);
            const barStartLocal = toLocalTime(barStartUtc);

            if (barStartLocal === lastCandleSnap.time) {
                // Same bar
                const updated = {
                    time: lastCandleSnap.time,
                    open: lastCandleSnap.open,
                    high: Math.max(lastCandleSnap.high, price),
                    low: Math.min(lastCandleSnap.low, price),
                    close: price,
                };
                candleSeries.update(updated);

                // ✅ DEBUG: Log line series update
                console.log(`[TICK UPDATE] Price: ${price.toFixed(5)}, Time: ${barStartLocal}`);

                // ✅ Update line series with NEW data point
                // This creates a continuous line that moves every tick
                lineSeries.update({
                    time: barStartLocal,
                    value: price,  // ← Use live price, not close!
                });

                updateOHLC(updated.open, updated.high, updated.low, updated.close);

            } else if (barStartLocal > lastCandleSnap.time) {
                // New bar
                const newCandle = {
                    time: barStartLocal,
                    open: lastCandleSnap.close,
                    high: Math.max(lastCandleSnap.close, price),
                    low: Math.min(lastCandleSnap.close, price),
                    close: price,
                };
                candleSeries.update(newCandle);

                // ✅ Update line series too
                lineSeries.update({
                    time: barStartLocal,
                    value: price,
                });

                lastCandleSnap = newCandle;
                updateOHLC(newCandle.open, newCandle.high, newCandle.low, newCandle.close);
                console.log(`[NEW CANDLE] ${currentTimeframe}`);
            }

            apiErrorCount = 0;

        } catch (e) {
            console.debug('[INFO] pollLiveTick: ' + e.message);
            liveBadge.textContent = '[ERROR] MT5 Offline';
            liveBadge.style.background = '#ef4444';
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // POLLING
    // ═══════════════════════════════════════════════════════════════════════

    function restartPolling() {
        if (tickInterval) clearInterval(tickInterval);
        if (latestInterval) clearInterval(latestInterval);

        tickInterval = setInterval(pollLiveTick, 1000);
        latestInterval = setInterval(pollLatestCandle, 30000);

        console.log('[OK] Polling restarted');
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    symbolSelect?.addEventListener('change', e => {
        currentSymbol = e.target.value;
        lastCandleSnap = null;
        apiErrorCount = 0;
        fetchAndDraw();
        restartPolling();
    });

    // ═══════════════════════════════════════════════════════════════════════
    // BOOT
    // ═══════════════════════════════════════════════════════════════════════

    console.log('[START] Dashboard initializing');

    try {
        initChart();
        await loadSymbols();
        await loadTimeframes();
        await fetchAndDraw();
        restartPolling();

        console.log('[OK] Dashboard ready');

    } catch (e) {
        console.error('[FAILED] Bootstrap:', e);
        liveBadge.textContent = '[ERROR] Init Failed';
        liveBadge.style.background = '#dc2626';
    }

})();
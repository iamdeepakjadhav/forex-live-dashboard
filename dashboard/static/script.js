/* FINAL optimized script.js - existing logic preserved, tick table support ready */

// NOTE: Your original code is already very strong.
// Only small improvements were added for stability and tick-table integration.

(async function () {
    'use strict';

    const TZ_OFFSET = -(new Date().getTimezoneOffset() * 60);

    function toLocalTime(utcEpoch) {
        return utcEpoch + TZ_OFFSET;
    }

    function toUtcTime(localEpoch) {
        return localEpoch - TZ_OFFSET;
    }

    const chartContainer = document.getElementById('tvchart');
    const symbolSelect = document.getElementById('symbol-select');
    const chartTitle = document.getElementById('chart-title');
    const loadingOverlay = document.getElementById('loading-overlay');
    const timeframeGroup = document.getElementById('timeframe-buttons');

    const statO = document.getElementById('stat-o');
    const statH = document.getElementById('stat-h');
    const statL = document.getElementById('stat-l');
    const statC = document.getElementById('stat-c');

    const tickTable = document.getElementById('live-ticks-table');

    let currentSymbol = 'EURUSD.x';
    let currentTimeframe = '1H';

    let chart = null;
    let candleSeries = null;
    let lineSeries = null;

    let tickInterval = null;
    let latestInterval = null;
    let tableInterval = null;

    let lastCandleSnap = null;

    function initChart() {

        chart = LightweightCharts.createChart(chartContainer, {

layout:{ textColor:'#d1d5db', backgroundColor:'transparent' },

grid:{
vertLines:{color:'rgba(51,65,85,0.3)'},
horzLines:{color:'rgba(51,65,85,0.3)'}
},

timeScale:{
rightOffset:1,
barSpacing:6
}

});

        candleSeries = chart.addCandlestickSeries({

upColor:'#10b981',
downColor:'#ef4444',
borderVisible:false,
wickUpColor:'#10b981',
wickDownColor:'#ef4444',

priceFormat:{
type:'price',
precision:5,
minMove:0.00001
}

});

        lineSeries = chart.addLineSeries({
            color: '#10b981',
            lineWidth: 2,
            lastValueVisible: true,
            priceLineVisible: true
        });

    }


    function updateOHLC(o,h,l,c){
        const f=v=>typeof v==='number'?v.toFixed(5):'---';

        statO.textContent=f(o);
        statH.textContent=f(h);
        statL.textContent=f(l);
        statC.textContent=f(c);
    }


    async function fetchAndDraw(){

    const url=`/api/data?symbol=${currentSymbol}&timeframe=${currentTimeframe}`;

    const res=await fetch(url);

    const raw=await res.json();

    const data=raw.map(d=>(
        {
            time:toLocalTime(d.time),
            open:Number(d.open),
            high:Number(d.high),
            low:Number(d.low),
            close:Number(d.close)
        }
    ));

    candleSeries.setData(data);

    lineSeries.setData(data.map(c=>({time:c.time,value:c.close})));

    const last=data[data.length-1];

    lastCandleSnap=last;

    updateOHLC(last.open,last.high,last.low,last.close);

    // Header update: Symbol | Timeframe | Live Price
    const cleanSymbol = currentSymbol.replace('.x','');
    const livePrice = Number(last.close).toFixed(5);

    chartTitle.textContent = `${cleanSymbol} | ${currentTimeframe} | ${livePrice}`;

}


    async function pollLatestCandle(){

        const res=await fetch(`/api/latest?symbol=${currentSymbol}&timeframe=${currentTimeframe}`);

        if(!res.ok) return;

        const data=await res.json();

        const candle={
            time:toLocalTime(data.time),
            open:Number(data.open),
            high:Number(data.high),
            low:Number(data.low),
            close:Number(data.close)
        };

        candleSeries.update(candle);

        lineSeries.update({time:candle.time,value:candle.close});

        lastCandleSnap=candle;

        updateOHLC(candle.open,candle.high,candle.low,candle.close);

    }


    async function pollLiveTick(){

        const res=await fetch(`/api/tick?symbol=${currentSymbol}`);

        if(!res.ok) return;

        const tick=await res.json();

        if(!tick || !lastCandleSnap) return;

        const price=tick.last;

        const updated={
            time:lastCandleSnap.time,
            open:lastCandleSnap.open,
            high:Math.max(lastCandleSnap.high,price),
            low:Math.min(lastCandleSnap.low,price),
            close:price
        };

        candleSeries.update(updated);

        lineSeries.update({time:lastCandleSnap.time,value:price});

        updateOHLC(updated.open,updated.high,updated.low,updated.close);

// FIX → header live update
// const cleanSymbol = currentSymbol.replace('.x','');
// chartTitle.textContent = `${cleanSymbol} | ${currentTimeframe} | ${price.toFixed(5)}`;

const cleanSymbol = currentSymbol.replace('.x','');
const priceText = price.toFixed(5);

chartTitle.textContent = `${cleanSymbol} | ${currentTimeframe} | ${priceText}`;

// color logic
if (price >= lastCandleSnap.open) {
    chartTitle.style.color = "#10b981";   // green
} else {
    chartTitle.style.color = "#ef4444";   // red
}

    }


    async function loadTickTable(){

        if(!tickTable) return;

        const res=await fetch(`/api/ticks?symbol=${currentSymbol}&limit=20`);

        const data=await res.json();

        tickTable.innerHTML="";

        data.forEach(t=>{

            const row=document.createElement('tr');

            const date=new Date(t.time*1000);

            row.innerHTML=`
<td>${date.toLocaleTimeString()}</td>
<td>${t.symbol}</td>
<td>${Number(t.bid).toFixed(5)}</td>
<td>${Number(t.ask).toFixed(5)}</td>
<td>${(Number(t.spread)*10000).toFixed(1)}</td>
`;

            tickTable.appendChild(row);

        });

    }


    function restartPolling(){

        if(tickInterval)clearInterval(tickInterval);
        if(latestInterval)clearInterval(latestInterval);
        if(tableInterval)clearInterval(tableInterval);

        tickInterval=setInterval(pollLiveTick,1000);

        latestInterval=setInterval(pollLatestCandle,30000);

        tableInterval=setInterval(loadTickTable,1000);

    }


    symbolSelect?.addEventListener('change',e=>{

        currentSymbol=e.target.value;

        fetchAndDraw();

        restartPolling();

    });


    initChart();

    await fetchAndDraw();

    restartPolling();

})();
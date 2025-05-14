import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, UTCTimestamp, SeriesMarker, SeriesMarkerPosition, SeriesMarkerShape } from 'lightweight-charts';
import type { KLineData, TradeMarkerData } from '../../types'; // Adjust path as necessary
import { fetchHistoricalKlines } from '../../api'; // Adjust path as necessary

interface RealtimeChartDisplayProps {
  symbol: string;
  interval: string; // e.g., "1m", "5m", "1h", "1d"
  runId?: string | null; // New prop
  latestTick?: KLineData; // Prop for the latest price tick data
  trades?: TradeMarkerData[]; // Prop for trade markers
}

const RealtimeChartDisplay: React.FC<RealtimeChartDisplayProps> = ({ symbol, interval, runId, latestTick, trades }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const candlestickSeriesApiRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Unified state for loading and error to simplify logic
  const [chartState, setChartState] = useState<{ isLoading: boolean; error: string | null }>({ isLoading: true, error: null });

  useEffect(() => {
    if (!chartContainerRef.current) {
      console.warn("[RealtimeChartDisplay EFFECT] chartContainerRef.current is null even though the div should always be rendered. This is unexpected. Further chart operations will likely fail or wait.");
      // We keep isLoading: true from initial state, or if it was set by a symbol/interval change before this check.
      // No need to setChartState here if it's already loading.
      // If for some reason it was false, it implies a bigger issue.
      return; // Wait for the ref to be available, though it should be.
    }

    // Initialize chart if it hasn't been initialized yet for this container
    if (!chartApiRef.current) {
      console.log("[RealtimeChartDisplay EFFECT] Initializing chart and series.");
      const chart = createChart(chartContainerRef.current, {
        width: chartContainerRef.current.clientWidth,
        height: 400,
        layout: {
          background: { type: ColorType.Solid, color: '#ffffff' },
          textColor: '#333',
        },
        grid: {
          vertLines: { color: 'rgba(197, 203, 206, 0.2)' },
          horzLines: { color: 'rgba(197, 203, 206, 0.2)' },
        },
        timeScale: {
          borderColor: 'rgba(197, 203, 206, 0.8)',
          timeVisible: true,
          secondsVisible: false,
        },
      });
      const series = chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderDownColor: '#ef5350',
        borderUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        wickUpColor: '#26a69a',
      });
      chartApiRef.current = chart;
      candlestickSeriesApiRef.current = series;
    }

    // At this point, chart and series should be initialized, and container ref is valid.
    // Proceed to load data.
    if (!symbol || !interval) {
        console.log(`[RealtimeChartDisplay EFFECT] Symbol ('${symbol}') or Interval ('${interval}') is missing. Clearing chart and not loading.`);
        if(candlestickSeriesApiRef.current) candlestickSeriesApiRef.current.setData([]);
        setChartState({ isLoading: false, error: "Symbol or Interval missing" });
        return;
    }
    
    console.log(`[RealtimeChartDisplay EFFECT] Fetching data for ${symbol}@${interval}`);
    setChartState({ isLoading: true, error: null }); // Set loading true before fetch
    let isActive = true;

    fetchHistoricalKlines(symbol, interval, 200)
      .then(klines => {
        if (isActive && candlestickSeriesApiRef.current) {
          const chartData: CandlestickData[] = klines.map(k => ({
            time: k.time as UTCTimestamp,
            open: k.open,
            high: k.high,
            low: k.low,
            close: k.close,
          }));
          candlestickSeriesApiRef.current.setData(chartData);
          console.log(`[RealtimeChartDisplay EFFECT] Data loaded and set for ${symbol}@${interval}. Count: ${chartData.length}`);
          if (isActive) setChartState({ isLoading: false, error: null });
        }
      })
      .catch(err => {
        console.error("[RealtimeChartDisplay EFFECT] Error fetching initial kline data:", err);
        if (isActive) setChartState({ isLoading: false, error: err.message || 'Failed to load chart data' });
      });

    // Resize handler setup (only once per chart instance)
    // This should ideally be tied to chartApiRef.current creation more directly
    const handleResize = () => {
      if (chartApiRef.current && chartContainerRef.current) {
        chartApiRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      isActive = false;
      window.removeEventListener('resize', handleResize);
      // Do NOT remove the chart here if symbol/interval changes.
      // Only remove on component unmount.
      // If symbol/interval becomes invalid, we clear data above.
      console.log("[RealtimeChartDisplay EFFECT] Cleanup for effect triggered by symbol/interval change.");
    };
  }, [symbol, interval, runId]); // Add runId to dependencies

  // Effect for component unmount cleanup
  useEffect(() => {
    return () => {
        console.log("[RealtimeChartDisplay UNMOUNT] Component unmounting. Removing chart.");
        if (chartApiRef.current) {
            chartApiRef.current.remove();
            chartApiRef.current = null;
        }
        candlestickSeriesApiRef.current = null;
    }
  }, []);

  // Effect for handling live updates from latestTick prop
  useEffect(() => {
    if (latestTick && candlestickSeriesApiRef.current) {
      const candleData: CandlestickData = {
        time: latestTick.time as UTCTimestamp,
        open: latestTick.open,
        high: latestTick.high,
        low: latestTick.low,
        close: latestTick.close,
      };
      candlestickSeriesApiRef.current.update(candleData);
    }
  }, [latestTick]);

  // Effect for handling trade markers
  useEffect(() => {
    if (!candlestickSeriesApiRef.current) {
        // console.log("[RealtimeChartDisplay MARKERS] Series API not ready for markers.");
        return;
    }

    if (trades && trades.length > 0) {
      const markers: SeriesMarker<UTCTimestamp>[] = trades.map(trade => ({
        time: trade.timestamp as UTCTimestamp,
        position: trade.type === 'BUY' ? 'belowBar' : 'aboveBar',
        color: trade.type === 'BUY' ? '#26a69a' : '#ef5350',
        shape: trade.type === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: `  ${trade.type} @ ${trade.price.toFixed(2)}  `
      }));
      candlestickSeriesApiRef.current.setMarkers(markers);
      // console.log(`[RealtimeChartDisplay MARKERS] Applied ${markers.length} trade markers for ${symbol}@${interval}`);
    } else {
      candlestickSeriesApiRef.current.setMarkers([]);
      // console.log(`[RealtimeChartDisplay MARKERS] Cleared trade markers for ${symbol}@${interval}`);
    }
  }, [trades, candlestickSeriesApiRef.current]);

  return (
    <div ref={chartContainerRef} style={{ width: '100%', height: '400px', position: 'relative' }}>
      {chartState.isLoading && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backgroundColor: 'rgba(255, 255, 255, 0.7)', // Optional: semi-transparent overlay
          zIndex: 10 // Ensure it's above the chart if chart renders briefly before loading state kicks in
        }}>
          Loading chart...
        </div>
      )}
      {chartState.error && !chartState.isLoading && ( // Show error only if not also loading
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'red',
          backgroundColor: 'rgba(255, 255, 255, 0.7)',
          zIndex: 10
        }}>
          Error: {chartState.error}
        </div>
      )}
      {/* The chart itself will be created by lightweight-charts inside the div pointed to by chartContainerRef */}
    </div>
  );
};

export default RealtimeChartDisplay; 
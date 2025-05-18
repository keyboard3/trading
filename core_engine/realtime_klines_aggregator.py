from typing import Dict, Tuple, Optional, Any
from pydantic import BaseModel, Field
import time # For current timestamp if needed, though ticks should have their own
import math

# Define KLineData structure, similar to backend/main_api.py and frontend/src/types.ts
# This could be a shared model in the future.
class KLineData(BaseModel):
    time: int  # UNIX timestamp (seconds, UTC), start time of the K-line bar
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0 # Initialize volume to 0.0

class RealtimeKlinesAggregator:
    def __init__(self):
        # Stores the currently forming K-line bar for each (symbol, interval_str)
        self._current_klines: Dict[Tuple[str, str], KLineData] = {}
        # Optional: Store the last tick's price to use as open for a new bar if needed.
        # self._last_prices: Dict[Tuple[str, str], float] = {}

    def _get_interval_seconds(self, interval_str: str) -> int:
        """Converts interval string (e.g., '1m', '5m', '1h', '1d') to seconds."""
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        try:
            unit = interval_str[-1].lower()
            value = int(interval_str[:-1])
            if unit in multipliers:
                return value * multipliers[unit]
        except ValueError:
            pass # Fall through to raise error
        raise ValueError(f"Invalid interval_str format: {interval_str}. Supported formats: e.g., 1m, 5m, 1h, 1d.")

    def _align_timestamp_to_interval(self, timestamp: float, interval_seconds: int) -> int:
        """Aligns a raw timestamp to the start of its K-line interval."""
        return int(math.floor(timestamp / interval_seconds) * interval_seconds)

    def update_with_tick(self, symbol: str, price: float, timestamp: float, volume: Optional[float], interval_str: str):
        """
        Updates the K-line data for the given symbol and interval with a new tick.
        timestamp: UNIX timestamp in seconds for the tick.
        volume: Volume for this specific tick, not cumulative for the bar yet.
        """
        try:
            interval_seconds = self._get_interval_seconds(interval_str)
        except ValueError:
            print(f"Warning: [KlinesAggregator] Invalid interval string '{interval_str}' for symbol '{symbol}'. Tick ignored for this interval.")
            return

        kline_start_time = self._align_timestamp_to_interval(timestamp, interval_seconds)
        key = (symbol, interval_str)

        current_bar = self._current_klines.get(key)
        tick_volume = volume if volume is not None else 0.0

        if current_bar is None or current_bar.time != kline_start_time:
            # New K-line bar
            # For a new bar, the first tick's price is open, high, low, close.
            new_bar = KLineData(
                time=kline_start_time,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=tick_volume
            )
            self._current_klines[key] = new_bar
            # self._last_prices[key] = price # Store for potential future use if open logic changes
        else:
            # Update existing K-line bar
            current_bar.high = max(current_bar.high, price)
            current_bar.low = min(current_bar.low, price)
            current_bar.close = price
            current_bar.volume = (current_bar.volume if current_bar.volume is not None else 0.0) + tick_volume
            # self._last_prices[key] = price

    def get_current_kline(self, symbol: str, interval_str: str) -> Optional[KLineData]:
        """
        Retrieves the currently formed K-line bar for the given symbol and interval.
        Returns a copy to prevent external modification if the stored object is mutable,
        though Pydantic models are generally immutable unless configured otherwise.
        """
        bar = self._current_klines.get((symbol, interval_str))
        return bar.model_copy() if bar else None

    def reset_symbol_interval(self, symbol: str, interval_str: str):
        """Resets the K-line data for a specific symbol and interval."""
        key = (symbol, interval_str)
        if key in self._current_klines:
            del self._current_klines[key]
        # if key in self._last_prices:
        #     del self._last_prices[key]
        print(f"[KlinesAggregator] Reset K-line data for {symbol} - {interval_str}")
        
    def reset_all(self):
        """Resets all K-line data."""
        self._current_klines.clear()
        # self._last_prices.clear()
        print(f"[KlinesAggregator] All K-line data reset.")

if __name__ == '__main__':
    # Example Usage:
    aggregator = RealtimeKlinesAggregator()
    
    # Simulate some ticks for MSFT, 1-minute interval
    ticks_msft_1m = [
        (100.00, time.time() + 0, 10),       # Bar 1 start
        (100.50, time.time() + 10, 12),
        (100.20, time.time() + 20, 8),
        (100.80, time.time() + 58, 15),      # Bar 1 near end
        (101.00, time.time() + 60, 20),      # Bar 2 start (exactly 1 min later)
        (101.20, time.time() + 70, 5),
        (100.90, time.time() + 110, 13),     # Bar 2 near end
        (100.00, time.time() + 120, 30),     # Bar 3 start
    ]

    print("--- Simulating for MSFT 1m ---")
    for price, ts, vol in ticks_msft_1m:
        aggregator.update_with_tick("MSFT", price, ts, vol, "1m")
        current_kline = aggregator.get_current_kline("MSFT", "1m")
        if current_kline:
            print(f"Tick @ {ts:.0f} ({price=}, {vol=}) -> Current 1m K-Line: Time={current_kline.time}, O={current_kline.open}, H={current_kline.high}, L={current_kline.low}, C={current_kline.close}, V={current_kline.volume}")
        else:
            print(f"Tick @ {ts:.0f} ({price=}, {vol=}) -> No 1m K-Line yet")

    # Simulate for AAPL, 5-minute interval
    aggregator.reset_all() # Reset for a clean test
    print("\n--- Simulating for AAPL 5m ---")
    base_ts_aapl = time.time()
    ticks_aapl_5m = [
        (200.0, base_ts_aapl + 0, 100),        # Bar 1
        (201.0, base_ts_aapl + 60, 120),       # Bar 1
        (199.0, base_ts_aapl + 120, 80),      # Bar 1
        (200.5, base_ts_aapl + 290, 150),     # Bar 1
        (202.0, base_ts_aapl + 300, 200),     # Bar 2 (exactly 5 mins later)
        (202.5, base_ts_aapl + 330, 50),       # Bar 2
    ]
    for price, ts, vol in ticks_aapl_5m:
        aggregator.update_with_tick("AAPL", price, ts, vol, "5m")
        current_kline = aggregator.get_current_kline("AAPL", "5m")
        if current_kline:
            print(f"Tick @ {ts:.0f} ({price=}, {vol=}) -> Current 5m K-Line: Time={current_kline.time}, O={current_kline.open}, H={current_kline.high}, L={current_kline.low}, C={current_kline.close}, V={current_kline.volume}")

    print("\n--- Test get_current_kline for non-existent data ---")
    print(f"MSFT 10m (should be None): {aggregator.get_current_kline('MSFT', '10m')}")

    print("\n--- Test reset for symbol/interval ---")
    aggregator.reset_symbol_interval('AAPL', '5m')
    print(f"AAPL 5m after reset (should be None): {aggregator.get_current_kline('AAPL', '5m')}") 
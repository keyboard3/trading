import collections
import pandas as pd
from typing import Deque, Optional, Callable

from core_engine.realtime_feed import DataTick # Corrected path based on findings
from core_engine.trading_engine import SignalEvent   # Corrected path based on findings
from core_engine.realtime_feed_base import RealtimeDataProviderBase # For type hinting
from .rsi_strategy import _calculate_rsi_values # From同目录的rsi_strategy.py导入

class RealtimeRSIStrategy:
    def __init__(self, 
                 symbol: str, 
                 period: int, 
                 oversold_threshold: float, 
                 overbought_threshold: float, 
                 signal_callback: Callable[[SignalEvent], None],
                 verbose: bool = False):

        self.symbol = symbol
        self.period = int(period) 
        self.oversold_threshold = float(oversold_threshold)
        self.overbought_threshold = float(overbought_threshold)
        self.signal_callback = signal_callback
        self.verbose = verbose

        self.price_history: Deque[float] = collections.deque(maxlen=self.period + 5) 
        self.current_rsi: Optional[float] = None
        self.previous_rsi: Optional[float] = None
        
        self.ticks_received = 0
        self.min_ticks_for_signal = self.period + 1 

        if self.verbose:
            print(f"RealtimeRSIStrategy [{self.symbol}] initialized: Period={self.period}, OS={self.oversold_threshold}, OB={self.overbought_threshold}, MinTicksForSignal={self.min_ticks_for_signal}")

    def _update_rsi(self) -> Optional[float]:
        """
        内部方法，使用价格历史计算最新的RSI值。
        返回最新的RSI值，如果数据不足则返回None。
        """
        if len(self.price_history) < self.period:
            return None

        current_prices = pd.Series(list(self.price_history), dtype=float)
        rsi_series = _calculate_rsi_values(current_prices, self.period)
        
        if not rsi_series.empty and pd.notna(rsi_series.iloc[-1]):
            return float(rsi_series.iloc[-1])
        return None

    def on_new_tick(self, tick: DataTick):
        if tick.symbol != self.symbol:
            return

        self.ticks_received += 1
        self.price_history.append(tick.price)

        if self.verbose:
            print(f"RealtimeRSIStrategy [{self.symbol}] Tick {self.ticks_received}: Price={tick.price:.2f}, HistoryLen={len(self.price_history)}")

        # 预热阶段逻辑
        if self.ticks_received < self.min_ticks_for_signal:
            if self.ticks_received >= self.period: # 当收集到足够数据计算第一个RSI时
                self.current_rsi = self._update_rsi() 
                if self.verbose and self.current_rsi is not None:
                    print(f"RealtimeRSIStrategy [{self.symbol}] Warming up, current RSI: {self.current_rsi:.2f} (tick {self.ticks_received})")
            
            # 可选：发送WARMING_UP信号给引擎，或仅在verbose时打印
            # signal_type = "WARMING_UP" 
            # generated_signal = SignalEvent(...) 
            # self.signal_callback(generated_signal)
            if self.verbose:
                 print(f"RealtimeRSIStrategy [{self.symbol}] WARMING_UP. Ticks: {self.ticks_received}/{self.min_ticks_for_signal}. Current RSI (if calculable): {self.current_rsi if self.current_rsi is not None else 'N/A'}")
            return

        # 数据充足，计算RSI并生成信号
        self.previous_rsi = self.current_rsi 
        self.current_rsi = self._update_rsi()

        signal_type = "HOLD" # 默认信号
        details = {}

        if self.current_rsi is None or self.previous_rsi is None:
            signal_type = "ERROR_RSI_CALC"
            details = {"message": "RSI calculation resulted in None or previous RSI is None."}
            if self.verbose:
                print(f"RealtimeRSIStrategy [{self.symbol}] ERROR_RSI_CALC. CurrentRSI: {self.current_rsi}, PreviousRSI: {self.previous_rsi}")
        else:
            if self.verbose:
                 print(f"RealtimeRSIStrategy [{self.symbol}] PrevRSI: {self.previous_rsi:.2f}, CurrRSI: {self.current_rsi:.2f}, OS: {self.oversold_threshold}, OB: {self.overbought_threshold}")

            if self.previous_rsi <= self.oversold_threshold and self.current_rsi > self.oversold_threshold:
                signal_type = "BUY"
            elif self.previous_rsi >= self.overbought_threshold and self.current_rsi < self.overbought_threshold:
                signal_type = "SELL"
            
            # Ensure details always has rsi and prev_rsi, even if None, for consistent structure
            details = {"rsi": round(self.current_rsi,2) if self.current_rsi is not None else None, 
                       "prev_rsi": round(self.previous_rsi,2) if self.previous_rsi is not None else None,
                       "strategy_name": "RealtimeRSIStrategy" # Add strategy name to details for clarity
                       }
        
        # Construct SignalEvent as a dictionary literal with correct keys for the engine
        generated_signal: SignalEvent = {
            "symbol": self.symbol,
            "timestamp": tick.timestamp,
            "signal": signal_type,  # Changed from signal_type to signal
            "price": tick.price,     # Changed from price_at_signal to price
            # "strategy_name": "RealtimeRSIStrategy", # Removed from top level, added to details
            "details": details
        }

        if self.verbose:
            print(f"RealtimeRSIStrategy [{self.symbol}] Generated signal: {generated_signal.get('signal')} at {generated_signal.get('price'):.2f} with RSI {details.get('rsi', 'N/A')}")
        
        self.signal_callback(generated_signal)

    def start(self):
        if self.verbose:
            print(f"RealtimeRSIStrategy [{self.symbol}] starting and preparing for data.")
        self.price_history.clear()
        self.ticks_received = 0
        self.current_rsi = None
        self.previous_rsi = None

    def stop(self):
        if self.verbose:
            print(f"RealtimeRSIStrategy [{self.symbol}] stopping.")

# Example of how to use it (for testing, not part of the class):
if __name__ == '__main__':
    from core_engine.realtime_feed import MockRealtimeDataProvider

    print("--- RealtimeRSIStrategy Test --- (Requires manual observation of prints)")

    # Mock data provider
    config = [{'symbol': 'TEST_RSI', 'initial_price': 100, 'volatility': 0.01, 'interval_seconds': 0.1}]
    mock_provider = MockRealtimeDataProvider(symbols_config=config, verbose=False)

    # Mock signal callback
    def test_signal_handler(event: SignalEvent):
        print(f"TestSignalHandler Received: {event}")

    # Strategy instance
    rsi_strategy_realtime = RealtimeRSIStrategy(
        symbol='TEST_RSI',
        period=5, # Shorter period for faster testing
        oversold_threshold=30,
        overbought_threshold=70,
        signal_callback=test_signal_handler,
        verbose=True
    )

    # Start
    mock_provider.start() # Start provider first
    mock_provider.subscribe('TEST_RSI', rsi_strategy_realtime.on_new_tick)
    rsi_strategy_realtime.start() # Then strategy just resets its state

    try:
        print("Running for a few seconds to observe signals...")
        # Let it run for a bit
        collections.deque(maxlen=0) # Dummy operation to spend time or use time.sleep
        import time
        time.sleep(5) # Run for 5 seconds
    except KeyboardInterrupt:
        print("Test interrupted by user.")
    finally:
        # Stop
        rsi_strategy_realtime.stop()
        mock_provider.unsubscribe('TEST_RSI', rsi_strategy_realtime.on_new_tick)
        mock_provider.stop()
        print("--- RealtimeRSIStrategy Test Finished ---") 
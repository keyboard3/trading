import pandas as pd
from collections import deque
import time # For timestamping signals if desired
from typing import Deque, Optional, Dict, Any, Callable # For type hinting

# Attempt to import from core_engine. If this file is run standalone for other tests,
# these imports might fail if core_engine is not in PYTHONPATH.
# For actual integration, ensure proper package structure.
try:
    from core_engine.realtime_feed_base import RealtimeDataProviderBase
    from core_engine.realtime_feed import DataTick # Assuming DataTick = Dict[str, Any]
    # SignalEvent could be imported if packages are structured for it, 
    # otherwise, use Dict or define locally for type hinting.
    # from ..core_engine.trading_engine import SignalEvent # This might be problematic
except ImportError:
    # Define fallbacks if run standalone or if imports fail, for basic type hinting to work
    # This is not ideal for production but helps during isolated development/testing of strategy file
    print("Warning: Could not import from core_engine. Using placeholder types for RealtimeDataProviderBase and DataTick.")
    RealtimeDataProviderBase = object # Placeholder
    DataTick = Dict[str, Any]      # Placeholder

# Define SignalEvent type hint locally for the callback
SignalEventForCallback = Dict[str, Any] 

def dual_moving_average_strategy(data: pd.DataFrame, short_window: int, long_window: int, symbol_col: str = 'symbol', close_col: str = 'close'):
    """
    为给定的数据应用双均线交叉策略，并为每个股票代码独立计算。

    参数:
    data (pd.DataFrame): 包含OHLCV数据的DataFrame，必须有日期索引，
                         以及指定的收盘价列和股票代码列。
    short_window (int): 短期移动平均线的窗口期。
    long_window (int): 长期移动平均线的窗口期。
    symbol_col (str): DataFrame中表示股票代码的列名。默认为'symbol'。
    close_col (str): DataFrame中表示收盘价的列名。默认为'close'。

    返回:
    pd.DataFrame: 带有 'short_ma', 'long_ma', 和 'signal' 列的原始DataFrame。
                  'signal' 列: 1 表示买入, -1 表示卖出, 0 表示持有。
    """
    if not isinstance(data, pd.DataFrame):
        raise ValueError("输入数据必须是 Pandas DataFrame。")
    if short_window <= 0 or long_window <= 0:
        raise ValueError("均线窗口期必须为正整数。")
    if short_window >= long_window:
        raise ValueError("短期均线窗口必须小于长期均线窗口。")
    if close_col not in data.columns:
        raise ValueError(f"收盘价列 '{close_col}' 不在DataFrame中。")
    if symbol_col not in data.columns:
        # 如果没有symbol列，则假设数据是单一资产
        print(f"警告: 股票代码列 '{symbol_col}' 未找到。将数据视为单一资产处理。")
        temp_symbol_col = '_temp_symbol_'
        data[temp_symbol_col] = 'DEFAULT_ASSET' # 创建一个临时的symbol列
        result_df = _apply_ma_strategy_to_group(data.copy(), short_window, long_window, close_col, temp_symbol_col)
        result_df.drop(columns=[temp_symbol_col], inplace=True)
        return result_df

    # 按股票代码分组，并对每个组应用策略
    processed_groups = []
    for symbol, group_data in data.groupby(symbol_col):
        # print(f"正在处理股票代码: {symbol}")
        processed_group = _apply_ma_strategy_to_group(group_data.copy(), short_window, long_window, close_col, symbol_col)
        processed_groups.append(processed_group)

    if not processed_groups:
        return data # 如果没有数据或分组，返回原始数据

    # 合并处理后的分组
    final_df = pd.concat(processed_groups)
    return final_df.sort_index() # 按日期索引排序，以防万一

def _apply_ma_strategy_to_group(group_data: pd.DataFrame, short_window: int, long_window: int, close_col: str, symbol_col: str):
    """辅助函数，对单个股票代码的数据应用MA策略"""
    
    # 计算短期和长期移动平均线
    # 使用 .rolling().mean() 计算简单移动平均线 (SMA)
    group_data['short_ma'] = group_data[close_col].rolling(window=short_window, min_periods=1).mean()
    group_data['long_ma'] = group_data[close_col].rolling(window=long_window, min_periods=1).mean()

    # 生成信号
    # 初始信号为0 (持有)
    group_data['signal'] = 0
    
    # 当短期均线上穿长期均线时，产生买入信号 (1)
    # 条件1: 当前 short_ma > long_ma
    # 条件2: 上一个时间点的 short_ma <= long_ma
    buy_condition = (group_data['short_ma'] > group_data['long_ma']) & \
                    (group_data['short_ma'].shift(1) <= group_data['long_ma'].shift(1))
    group_data.loc[buy_condition, 'signal'] = 1

    # 当短期均线下穿长期均线时，产生卖出信号 (-1)
    # 条件1: 当前 short_ma < long_ma
    # 条件2: 上一个时间点的 short_ma >= long_ma
    sell_condition = (group_data['short_ma'] < group_data['long_ma']) & \
                     (group_data['short_ma'].shift(1) >= group_data['long_ma'].shift(1))
    group_data.loc[sell_condition, 'signal'] = -1
    
    # 填充因shift(1)操作产生的初始NaN信号（如果有必要，但这里交叉条件已处理）
    # group_data['signal'].fillna(0, inplace=True) # 通常不需要，因为我们初始化为0

    return group_data

class RealtimeSimpleMAStrategy:
    """
    A simple moving average crossover strategy adapted for real-time data ticks.
    Generates 'BUY', 'SELL', or 'HOLD' signals.
    """
    def __init__(self, 
                 symbol: str, 
                 short_window: int, 
                 long_window: int, 
                 data_provider: RealtimeDataProviderBase,
                 verbose: bool = False,
                 signal_callback: Optional[Callable[[SignalEventForCallback], None]] = None):
        if not isinstance(short_window, int) or not isinstance(long_window, int) or short_window <= 0 or long_window <= 0:
            raise ValueError("Window periods must be positive integers.")
        if short_window >= long_window:
            raise ValueError("Short window must be less than long window.")
        
        self.symbol: str = symbol
        self.short_window: int = short_window
        self.long_window: int = long_window
        self.data_provider: RealtimeDataProviderBase = data_provider
        self.verbose: bool = verbose
        self.signal_callback: Optional[Callable[[SignalEventForCallback], None]] = signal_callback

        self.prices: Deque[float] = deque(maxlen=long_window)
        self.short_ma: Optional[float] = None
        self.long_ma: Optional[float] = None
        self.prev_short_ma: Optional[float] = None
        self.prev_long_ma: Optional[float] = None
        
        self.current_signal: str = "WARMING_UP" # Initial state
        self.last_signal_timestamp: Optional[float] = None

    def _calculate_sma(self, window_size: int) -> Optional[float]:
        """Calculates Simple Moving Average if enough data is present."""
        if len(self.prices) >= window_size:
            # Take the last 'window_size' elements from the deque for calculation
            # Convert deque to list for slicing if not taking the whole deque part for sum
            # For SMA, sum of all elements in the relevant window is fine.
            if window_size == self.short_window:
                 # SMA for short window: sum of last short_window prices
                return sum(list(self.prices)[-self.short_window:]) / self.short_window
            elif window_size == self.long_window:
                 # SMA for long window: sum of all prices in the deque (since maxlen is long_window)
                return sum(self.prices) / len(self.prices) # or self.long_window if full
        return None

    def on_new_tick(self, data_tick: DataTick) -> None:
        """
        Callback function to process a new data tick from the provider.
        Updates MAs and generates a new signal if applicable.
        """
        if data_tick.symbol != self.symbol:
            return # Not for us

        new_price = data_tick.price
        current_timestamp = data_tick.timestamp # DataTick namedtuple ensures timestamp exists

        if self.verbose:
            print(f"[{time.ctime(current_timestamp)}] {self.symbol} STRATEGY: Received tick. Price: {new_price}, Timestamp: {current_timestamp}")

        if new_price is None: # Price can be None if data source has issues, though our mock provider always provides one.
            if self.verbose:
                print(f"[{time.ctime(current_timestamp)}] {self.symbol} STRATEGY: Received tick with no price data (or price was None): {data_tick}")
            return
            
        self.prices.append(float(new_price))

        if len(self.prices) < self.long_window:
            self.current_signal = "WARMING_UP"
            if self.verbose:
                print(f"[{time.ctime(current_timestamp)}] {self.symbol} STRATEGY: Warming up... {len(self.prices)}/{self.long_window} prices.")
            return

        # Store current MAs as previous before recalculating
        self.prev_short_ma = self.short_ma
        self.prev_long_ma = self.long_ma

        # Calculate new MAs
        self.short_ma = self._calculate_sma(self.short_window)
        self.long_ma = self._calculate_sma(self.long_window) # Should be sum(self.prices) / self.long_window if prices deque is full
        
        # Re-check long_ma calculation for correctness if deque is full
        if len(self.prices) == self.long_window:
            self.long_ma = sum(self.prices) / self.long_window
        else: # Should not happen if len(self.prices) >= self.long_window and maxlen is self.long_window
            # This case implies an issue if deque isn't full but len(prices) >= long_window was met.
            # However, _calculate_sma for long_window already uses len(self.prices), so this should be fine.
            # For clarity, ensure long_ma is what we expect if deque isn't full to its maxlen.
            if len(self.prices) >= self.long_window: # Redundant check if logic above is correct
                 self.long_ma = sum(self.prices) / len(self.prices) 
            else:
                 self.long_ma = None

        if self.verbose:
            print(f"[{time.ctime(current_timestamp)}] {self.symbol} STRATEGY: Calculated MAs. ShortMA: {self.short_ma}, LongMA: {self.long_ma}")

        if self.short_ma is None or self.long_ma is None:
            self.current_signal = "ERROR_MA_CALC" 
            if self.verbose:
                 print(f"[{time.ctime(current_timestamp)}] {self.symbol} STRATEGY: Error calculating MAs. Current prices buffer size: {len(self.prices)}. ShortMA: {self.short_ma}, LongMA: {self.long_ma}")
            return

        # Signal generation logic
        new_signal_generated_this_tick = False
        previous_signal_state = self.current_signal

        if self.prev_short_ma is not None and self.prev_long_ma is not None: # Ensure previous MAs exist for crossover detection
            # Buy signal: short MA crosses above long MA
            if self.prev_short_ma <= self.prev_long_ma and self.short_ma > self.long_ma:
                self.current_signal = "BUY"
                new_signal_generated_this_tick = True
            # Sell signal: short MA crosses below long MA
            elif self.prev_short_ma >= self.prev_long_ma and self.short_ma < self.long_ma:
                self.current_signal = "SELL"
                new_signal_generated_this_tick = True
            else: # No new crossover
                if self.current_signal in ["WARMING_UP", "ERROR_MA_CALC"]:
                    self.current_signal = "HOLD"
                    new_signal_generated_this_tick = True # Transition from WARMING_UP/ERROR to HOLD is a notable event
        
        elif self.current_signal == "WARMING_UP": # First time MAs are valid after warming up
             self.current_signal = "HOLD" # Initial signal after warm-up is HOLD
             new_signal_generated_this_tick = True

        if new_signal_generated_this_tick or (self.verbose and previous_signal_state != self.current_signal):
            self.last_signal_timestamp = current_timestamp
            # This verbose print is already good, captures Price, MAs, and Signal
            if self.verbose:
                print(f"[{time.ctime(self.last_signal_timestamp)}] {self.symbol} STRATEGY: Price={new_price:.2f}, "
                      f"ShortMA={self.short_ma:.2f}, LongMA={self.long_ma:.2f} -> New Signal={self.current_signal} (Previous: {previous_signal_state})")
            
            if self.signal_callback:
                event: SignalEventForCallback = {
                    'symbol': self.symbol,
                    'timestamp': self.last_signal_timestamp,
                    'signal': self.current_signal,
                    'price': float(new_price) # Ensure price is float
                }
                if self.verbose:
                    print(f"[{time.ctime(self.last_signal_timestamp)}] {self.symbol} STRATEGY: Sending signal event: {event}")
                try:
                    self.signal_callback(event)
                except Exception as e:
                    print(f"Error in signal_callback for {self.symbol}: {e}")
                  
    def get_latest_signal(self) -> str:
        """Returns the latest generated signal."""
        return self.current_signal

    def start(self) -> None:
        """Subscribes the strategy to the data provider for its symbol."""
        if self.verbose:
            print(f"RealtimeSimpleMAStrategy for {self.symbol}: Subscribing to data provider.")
        # Ensure the callback is properly bound if passing instance methods
        self.data_provider.subscribe(self.symbol, self.on_new_tick)

    def stop(self) -> None:
        """Unsubscribes the strategy from the data provider."""
        if self.verbose:
            print(f"RealtimeSimpleMAStrategy for {self.symbol}: Unsubscribing from data provider.")
        self.data_provider.unsubscribe(self.symbol, self.on_new_tick)

if __name__ == '__main__':
    # 简单的测试代码
    # 构造一个示例 DataFrame (模拟 data_loader.py 的输出)
    sample_data = {
        'Date': pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05',
                                '2023-01-06', '2023-01-07', '2023-01-08', '2023-01-09', '2023-01-10',
                                '2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05',
                                '2023-01-06', '2023-01-07', '2023-01-08', '2023-01-09', '2023-01-10']),
        'close': [10, 12, 11, 13, 15, 14, 16, 18, 17, 19,
                  20, 18, 19, 17, 16, 15, 14, 13, 12, 11],
        'open': [9, 11, 10, 12, 14, 13, 15, 17, 16, 18,
                 21, 19, 18, 16, 17, 16, 15, 14, 13, 12 ],
        'symbol': ['AAA'] * 10 + ['BBB'] * 10
    }
    df = pd.DataFrame(sample_data)
    df.set_index('Date', inplace=True)

    print("原始数据:")
    print(df)

    # 应用策略
    short_w = 3
    long_w = 6
    df_with_signals = dual_moving_average_strategy(df.copy(), short_window=short_w, long_window=long_w) # 使用默认列名 'close' 和 'symbol'
    
    print(f"\n应用MA策略 (short_w={short_w}, long_w={long_w}) 后的数据:")
    print(df_with_signals[['symbol', 'close', 'short_ma', 'long_ma', 'signal']])

    # 测试无symbol列的情况
    df_single = df[df['symbol'] == 'AAA'].drop(columns=['symbol'])
    print("\n原始数据 (单一资产, 无symbol列):")
    print(df_single)
    df_single_with_signals = dual_moving_average_strategy(df_single.copy(), short_window=short_w, long_window=long_w)
    print(f"\n应用MA策略 (单一资产) 后的数据:")
    print(df_single_with_signals[['close', 'short_ma', 'long_ma', 'signal']]) 
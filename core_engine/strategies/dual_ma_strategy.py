'''
Dual Moving Average Crossover Strategy
'''
import pandas as pd
from .base_strategy import BaseStrategy
from typing import Dict, Any, List

class DualMAStrategy(BaseStrategy):
    _strategy_name = "DualMAStrategy"
    _strategy_display_name = "Dual Moving Average Crossover"
    _description = "A simple strategy that buys when a short-term MA crosses above a long-term MA, and sells when it crosses below."
    _parameters = {
        "short_window": {"type": "int", "default": 20, "min": 5, "max": 100, "label_cn": "短期MA周期"},
        "long_window": {"type": "int", "default": 50, "min": 10, "max": 200, "label_cn": "长期MA周期"}
    }
    # _default_indicator_columns = ['short_ma', 'long_ma'] # Can be removed

    def __init__(self, params: Dict[str, Any], data: pd.DataFrame, initial_capital: float):
        super().__init__(params, data, initial_capital)
        self.short_window = int(self.params.get("short_window", self._parameters["short_window"]["default"]))
        self.long_window = int(self.params.get("long_window", self._parameters["long_window"]["default"]))
        
        if self.short_window >= self.long_window:
            print(f"Warning: DualMAStrategy short_window ({self.short_window}) is not less than long_window ({self.long_window}).")

        self.generated_indicator_columns: List[str] = [] # Initialize instance attribute
        self._prepare_data()

    def _prepare_data(self):
        # Using dynamic column names based on window size for clarity in plots
        self.col_short_ma = f'MA{self.short_window}' # Store as instance attribute
        self.col_long_ma = f'MA{self.long_window}'   # Store as instance attribute
        self.data[self.col_short_ma] = self.data['close'].rolling(window=self.short_window).mean()
        self.data[self.col_long_ma] = self.data['close'].rolling(window=self.long_window).mean()
        self.generated_indicator_columns = [self.col_short_ma, self.col_long_ma]

    def _generate_signals(self) -> pd.Series:
        refined_signals = pd.Series(index=self.data.index, data=0)
        position = 0 # 0: no position, 1: long position

        # Ensure we have at least one previous data point for crossover detection
        # and enough data for the longest MA.
        # The loop should start from an index where self.data['long_ma'].iloc[i-1] is valid.
        # The rolling mean for long_window will produce NaNs for the first long_window - 1 entries.
        # So, valid data for long_ma starts at index long_window - 1.
        # To access iloc[i-1] for long_ma, i-1 must be >= long_window - 1, so i must be >= long_window.
        start_loop_index = self.long_window 
        if start_loop_index < 1: # Handle cases with very small window if necessary, though unlikely for MA
            start_loop_index = 1 

        for i in range(start_loop_index, len(self.data)):
            # Skip if MA data is not available (NaNs at the beginning of the series)
            if pd.isna(self.data[self.col_short_ma].iloc[i]) or pd.isna(self.data[self.col_long_ma].iloc[i]) or \
               pd.isna(self.data[self.col_short_ma].iloc[i-1]) or pd.isna(self.data[self.col_long_ma].iloc[i-1]):
                continue

            # Bullish Crossover: short_ma crosses above long_ma
            is_bullish_crossover = (self.data[self.col_short_ma].iloc[i-1] <= self.data[self.col_long_ma].iloc[i-1]) and \
                                 (self.data[self.col_short_ma].iloc[i] > self.data[self.col_long_ma].iloc[i])
            
            # Bearish Crossover: short_ma crosses below long_ma
            is_bearish_crossover = (self.data[self.col_short_ma].iloc[i-1] >= self.data[self.col_long_ma].iloc[i-1]) and \
                                 (self.data[self.col_short_ma].iloc[i] < self.data[self.col_long_ma].iloc[i])

            if is_bullish_crossover:
                if position == 0: # If not in position, buy
                    refined_signals.iloc[i] = 1
                    position = 1
            elif is_bearish_crossover:
                if position == 1: # If in position, sell
                    refined_signals.iloc[i] = -1
                    position = 0
            # else: signals remain 0 (Hold)
        
        return refined_signals

    # get_info is inherited from BaseStrategy
    # get_default_params is inherited from BaseStrategy


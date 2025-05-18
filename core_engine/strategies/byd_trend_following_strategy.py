'''
BYD Inspired Trend Following Strategy

This strategy is inspired by the analysis document for BYD (002594.SZ),
focusing on trend-following using multiple moving averages, volume confirmation,
and includes stop-loss and take-profit mechanisms.
'''
import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
from typing import Dict, Any, List

class BYDTrendFollowingStrategy(BaseStrategy):
    _strategy_name = "BYDTrendFollowingStrategy"
    _strategy_display_name = "BYD Inspired Trend Following"
    _description = "A trend-following strategy using multiple MAs, volume confirmation, stop-loss, and take-profit."
    _parameters = {
        "short_ma_period": {"type": "int", "default": 20, "min": 5, "max": 50, "label_cn": "短期MA周期"},
        "medium_ma_period": {"type": "int", "default": 60, "min": 20, "max": 100, "label_cn": "中期MA周期"},
        "long_ma_period": {"type": "int", "default": 120, "min": 50, "max": 200, "label_cn": "长期MA周期"},
        "volume_avg_period": {"type": "int", "default": 20, "min": 5, "max": 50, "label_cn": "成交量平均周期"},
        "volume_threshold_multiplier": {"type": "float", "default": 1.5, "min": 1.0, "max": 3.0, "step": 0.1, "label_cn": "成交量放大倍数"},
        "stop_loss_percentage": {"type": "float", "default": 0.08, "min": 0.01, "max": 0.2, "step": 0.01, "label_cn": "止损百分比"},
        "take_profit_percentage": {"type": "float", "default": 0.20, "min": 0.05, "max": 0.5, "step": 0.01, "label_cn": "止盈百分比"},
        "initial_position_ratio": {"type": "float", "default": 0.3, "min": 0.1, "max": 1.0, "step": 0.05, "label_cn": "初始仓位比例"}
    }
    # _default_indicator_columns can be removed or commented out
    # _default_indicator_columns = [
    #     f\'MA{_parameters["short_ma_period"]["default"]}\', 
    #     f\'MA{_parameters["medium_ma_period"]["default"]}\', 
    #     f\'MA{_parameters["long_ma_period"]["default"]}\', 
    #     \'AvgVolume\'
    # ]

    def __init__(self, params: Dict[str, Any], data: pd.DataFrame, initial_capital: float):
        super().__init__(params, data, initial_capital)
        # Validate and store parameters
        self.short_ma_period = int(self.params.get("short_ma_period", self._parameters["short_ma_period"]["default"]))
        self.medium_ma_period = int(self.params.get("medium_ma_period", self._parameters["medium_ma_period"]["default"]))
        self.long_ma_period = int(self.params.get("long_ma_period", self._parameters["long_ma_period"]["default"]))
        self.volume_avg_period = int(self.params.get("volume_avg_period", self._parameters["volume_avg_period"]["default"]))
        self.volume_threshold_multiplier = float(self.params.get("volume_threshold_multiplier", self._parameters["volume_threshold_multiplier"]["default"]))
        self.stop_loss_percentage = float(self.params.get("stop_loss_percentage", self._parameters["stop_loss_percentage"]["default"]))
        self.take_profit_percentage = float(self.params.get("take_profit_percentage", self._parameters["take_profit_percentage"]["default"]))
        self.initial_position_ratio = float(self.params.get("initial_position_ratio", self._parameters["initial_position_ratio"]["default"]))

        self.generated_indicator_columns: List[str] = [] # Initialize instance attribute
        # Prepare data with indicators
        self._prepare_data()

    def _prepare_data(self):
        print("\n[BYDTrendFollowingStrategy._prepare_data] Raw data head for close and volume:")
        print(self.data[['close', 'volume']].head())
        print("\n[BYDTrendFollowingStrategy._prepare_data] Raw data describe for close and volume:")
        print(self.data[['close', 'volume']].describe())

        self.generated_indicator_columns = [] # Reset in case of re-entry

        col_short_ma = f'MA{self.short_ma_period}'
        self.data[col_short_ma] = self.data['close'].rolling(window=self.short_ma_period).mean()
        self.generated_indicator_columns.append(col_short_ma)

        col_medium_ma = f'MA{self.medium_ma_period}'
        self.data[col_medium_ma] = self.data['close'].rolling(window=self.medium_ma_period).mean()
        self.generated_indicator_columns.append(col_medium_ma)

        col_long_ma = f'MA{self.long_ma_period}'
        self.data[col_long_ma] = self.data['close'].rolling(window=self.long_ma_period).mean()
        self.generated_indicator_columns.append(col_long_ma)

        col_avg_volume = 'AvgVolume' # Assuming fixed name for average volume
        self.data[col_avg_volume] = self.data['volume'].rolling(window=self.volume_avg_period).mean()
        self.generated_indicator_columns.append(col_avg_volume)

        print("\n[BYDTrendFollowingStrategy._prepare_data] Calculated indicators head:")
        print(self.data[self.generated_indicator_columns].head())
        print("\n[BYDTrendFollowingStrategy._prepare_data] Calculated indicators describe:")
        print(self.data[self.generated_indicator_columns].describe())

    def _generate_signals(self) -> pd.Series:
        signals = pd.Series(index=self.data.index, data=0)  # 0: Hold, 1: Buy, -1: Sell
        position = 0  # 0: No position, 1: Long position
        buy_price = 0.0

        for i in range(max(self.long_ma_period, self.volume_avg_period), len(self.data)):
            # Check for missing MA or AvgVolume values (common at the beginning)
            if pd.isna(self.data[f'MA{self.long_ma_period}'].iloc[i]) or \
               pd.isna(self.data[f'MA{self.medium_ma_period}'].iloc[i]) or \
               pd.isna(self.data[f'MA{self.short_ma_period}'].iloc[i]) or \
               pd.isna(self.data['AvgVolume'].iloc[i]):
                continue

            # Buy conditions
            ma_short = self.data[f'MA{self.short_ma_period}'].iloc[i]
            ma_medium = self.data[f'MA{self.medium_ma_period}'].iloc[i]
            ma_long = self.data[f'MA{self.long_ma_period}'].iloc[i]
            current_price = self.data['close'].iloc[i]
            current_volume = self.data['volume'].iloc[i]
            avg_volume = self.data['AvgVolume'].iloc[i]

            is_ma_bullish_aligned = ma_short > ma_medium > ma_long
            is_price_above_short_ma = current_price > ma_short
            is_volume_confirmed = current_volume > (avg_volume * self.volume_threshold_multiplier)
            
            if position == 0: # If no position
                if is_ma_bullish_aligned and is_price_above_short_ma and is_volume_confirmed:
                    signals.iloc[i] = 1  # Buy signal
                    position = 1
                    buy_price = current_price
            elif position == 1: # If holding a position
                # Sell conditions (Stop Loss)
                if current_price <= buy_price * (1 - self.stop_loss_percentage):
                    signals.iloc[i] = -1  # Sell signal (Stop Loss)
                    position = 0
                    buy_price = 0.0
                    continue # Processed sell for this tick

                # Sell conditions (Take Profit)
                if current_price >= buy_price * (1 + self.take_profit_percentage):
                    signals.iloc[i] = -1  # Sell signal (Take Profit)
                    position = 0
                    buy_price = 0.0
                    continue # Processed sell for this tick

                # Sell conditions (Trend Reversal - MA Crossover)
                if ma_short < ma_medium: # Simplified trend reversal signal
                    signals.iloc[i] = -1  # Sell signal (Trend Reversal)
                    position = 0
                    buy_price = 0.0
                    continue # Processed sell for this tick
        return signals

    @classmethod
    def get_info(cls) -> Dict[str, Any]:
        return {
            "name": cls._strategy_name,
            "display_name": cls._strategy_display_name,
            "description": cls._description,
            "parameters": cls._parameters
        } 
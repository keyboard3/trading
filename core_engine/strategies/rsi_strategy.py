'''
Relative Strength Index (RSI) Strategy
'''
import pandas as pd
from .base_strategy import BaseStrategy
from typing import Dict, Any, List

class RSIStrategy(BaseStrategy):
    _strategy_name = "RSIStrategy"
    _strategy_display_name = "Relative Strength Index (RSI)"
    _description = "Buys when RSI crosses above oversold, sells when RSI crosses below overbought."
    _parameters = {
        "period": {"type": "int", "default": 14, "min": 5, "max": 50, "label_cn": "RSI周期"},
        "oversold_threshold": {"type": "float", "default": 30.0, "min": 10.0, "max": 40.0, "step": 1.0, "label_cn": "超卖阈值"},
        "overbought_threshold": {"type": "float", "default": 70.0, "min": 60.0, "max": 90.0, "step": 1.0, "label_cn": "超买阈值"}
    }

    def __init__(self, params: Dict[str, Any], data: pd.DataFrame, initial_capital: float):
        super().__init__(params, data, initial_capital)
        self.period = int(self.params.get("period", self._parameters["period"]["default"]))
        self.oversold_threshold = float(self.params.get("oversold_threshold", self._parameters["oversold_threshold"]["default"]))
        self.overbought_threshold = float(self.params.get("overbought_threshold", self._parameters["overbought_threshold"]["default"]))
        self.generated_indicator_columns: List[str] = []
        self._prepare_data()

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff(1)
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _prepare_data(self):
        if 'close' not in self.data.columns:
            raise ValueError("Dataframe must contain 'close' column for RSI calculation.")
        self.data['rsi'] = self._calculate_rsi(self.data['close'], self.period)
        self.generated_indicator_columns = ['rsi']

    def _generate_signals(self) -> pd.Series:
        signals = pd.Series(index=self.data.index, data=0)
        position = 0 # 0: No position, 1: Long position

        # Start loop after RSI calculation period + 1 for crossover detection
        start_loop_index = self.period + 1
        if start_loop_index >= len(self.data):
            return signals # Not enough data

        for i in range(start_loop_index, len(self.data)):
            current_rsi = self.data['rsi'].iloc[i]
            prev_rsi = self.data['rsi'].iloc[i-1]

            if pd.isna(current_rsi) or pd.isna(prev_rsi):
                continue

            # Buy signal: RSI crosses above oversold threshold
            if prev_rsi <= self.oversold_threshold and current_rsi > self.oversold_threshold:
                if position == 0:
                    signals.iloc[i] = 1
                    position = 1
            # Sell signal: RSI crosses below overbought threshold
            elif prev_rsi >= self.overbought_threshold and current_rsi < self.overbought_threshold:
                if position == 1:
                    signals.iloc[i] = -1
                    position = 0
        return signals 
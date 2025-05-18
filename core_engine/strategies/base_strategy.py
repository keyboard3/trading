'''
Defines the base class for all trading strategies.
'''
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

class BaseStrategy(ABC):
    _strategy_name: str = "BaseStrategy"
    _strategy_display_name: str = "Base Strategy"
    _description: str = "This is a base class for trading strategies and should not be used directly."
    _parameters: Dict[str, Dict[str, Any]] = {}
    _default_indicator_columns: List[str] = []

    def __init__(self, params: Dict[str, Any], data: pd.DataFrame, initial_capital: float):
        self.params = params
        self.data = data.copy() # Work on a copy to avoid modifying original df in backtester
        self.initial_capital = initial_capital
        # self._prepare_data() # Child classes should call this if they have specific data prep needs

    @abstractmethod
    def _prepare_data(self):
        """
        Prepares the data with necessary indicators for the strategy.
        This method should be implemented by subclasses if they need to calculate indicators.
        If no indicators are needed beyond what's in the input data, this can be a pass.
        """
        pass

    @abstractmethod
    def _generate_signals(self) -> pd.Series:
        """
        Generates trading signals based on the strategy logic.
        Must be implemented by subclasses.

        Returns:
            pd.Series: A series with the same index as self.data, 
                       containing signals (1 for Buy, -1 for Sell, 0 for Hold).
        """
        pass

    @classmethod
    def get_info(cls) -> Dict[str, Any]:
        """
        Returns a dictionary containing the strategy's metadata.
        """
        return {
            "name": cls._strategy_name,
            "display_name": cls._strategy_display_name,
            "description": cls._description,
            "parameters": cls._parameters
        }

    @classmethod
    def get_default_params(cls) -> Dict[str, Any]:
        """Returns a dictionary of default parameters for the strategy."""
        return {key: val_dict["default"] for key, val_dict in cls._parameters.items() if "default" in val_dict} 
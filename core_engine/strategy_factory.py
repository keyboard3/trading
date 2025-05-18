'''Handles creation of strategy instances.'''
from typing import Dict, Type
from .strategies.base_strategy import BaseStrategy
from .strategies.dual_ma_strategy import DualMAStrategy
from .strategies.rsi_strategy import RSIStrategy
from .strategies.byd_trend_following_strategy import BYDTrendFollowingStrategy

# Mapping of strategy names to their classes
STRATEGY_MAP: Dict[str, Type[BaseStrategy]] = {
    DualMAStrategy.get_info()["name"]: DualMAStrategy,
    RSIStrategy.get_info()["name"]: RSIStrategy,
    BYDTrendFollowingStrategy.get_info()["name"]: BYDTrendFollowingStrategy,
}

def get_strategy_class(strategy_name: str) -> Type[BaseStrategy] | None:
    '''Retrieve a strategy class by its name.'''
    return STRATEGY_MAP.get(strategy_name)

def get_available_strategies() -> Dict[str, Dict]:
    '''Returns a dictionary of available strategies and their parameters.'''
    available = {}
    for name, cls in STRATEGY_MAP.items():
        info = cls.get_info()
        available[name] = {
            "display_name": info.get("display_name", name),
            "description": info.get("description", ""),
            "parameters": info.get("parameters", {})
        }
    return available 
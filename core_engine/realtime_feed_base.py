from abc import ABC, abstractmethod

class RealtimeDataProviderBase(ABC):
    """
    Abstract base class for real-time data providers.
    Defines the interface for subscribing to and receiving real-time market data.
    """

    @abstractmethod
    def subscribe(self, symbol: str, callback_function) -> None:
        """
        Subscribe to real-time data for a specific symbol.

        Args:
            symbol (str): The trading symbol to subscribe to (e.g., 'SIM_STOCK_A').
            callback_function: A function to be called when new data for the symbol is available.
                               This function should accept a single argument: a dictionary
                               representing the data tick (e.g., {'symbol': ..., 'timestamp': ..., 'price': ...}).
        """
        pass

    @abstractmethod
    def unsubscribe(self, symbol: str, callback_function) -> None:
        """
        Unsubscribe from real-time data for a specific symbol.

        Args:
            symbol (str): The trading symbol.
            callback_function: The callback function that was previously subscribed.
        """
        pass

    @abstractmethod
    def start(self) -> None:
        """
        Start the data provider.
        This might involve connecting to a data source or starting a data generation loop.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """
        Stop the data provider.
        This should gracefully shut down connections or data generation.
        """
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float | None:
        """
        Get the last known price for a specific symbol.

        Args:
            symbol (str): The trading symbol.

        Returns:
            Optional[float]: The last known price, or None if not available.
        """
        pass 
import time
import random
import threading
from typing import List, Dict, Callable, Any
import collections # Import collections
# Ensure this import path is correct based on your project structure.
# If realtime_feed.py and realtime_feed_base.py are in the same directory 'core_engine',
# and 'core_engine' is a package (has an __init__.py, or is added to sys.path),
# then relative import should work.
from .realtime_feed_base import RealtimeDataProviderBase

# Define the structure of the symbol configuration
SymbolConfig = Dict[str, Any]  # e.g., {'symbol': str, 'initial_price': float, ...}
# Define the structure of a data tick using namedtuple for attribute access
DataTick = collections.namedtuple('DataTick', ['symbol', 'timestamp', 'price'])


class MockRealtimeDataProvider(RealtimeDataProviderBase):
    """
    A mock real-time data provider that generates simulated price ticks.
    """

    def __init__(self, symbols_config: List[SymbolConfig], verbose: bool = False):
        """
        Initialize the mock data provider.

        Args:
            symbols_config: A list of dictionaries, where each dictionary configures a symbol.
                            Example: [
                                {'symbol': 'SIM_STOCK_A', 'initial_price': 10.00, 'volatility': 0.001, 'interval_seconds': 1.0},
                                {'symbol': 'SIM_CRYPTO_X', 'initial_price': 3000.00, 'volatility': 0.005, 'interval_seconds': 0.5}
                            ]
                            'volatility' is a factor for random price change.
                            'interval_seconds' is how often new prices are generated for this symbol.
            verbose: If True, enables detailed logging from the provider.
        """
        self._symbols_config: List[SymbolConfig] = symbols_config
        self.verbose: bool = verbose
        self._current_prices: Dict[str, float] = {
            config['symbol']: config['initial_price'] for config in symbols_config
        }
        self._last_update_times: Dict[str, float] = {
            config['symbol']: 0.0 for config in symbols_config
        }
        # Subscribers: Dict[symbol, List[callback_function]]
        self._subscribers: Dict[str, List[Callable[[DataTick], None]]] = {
            config['symbol']: [] for config in symbols_config
        }
        self._running: bool = False
        self._thread: threading.Thread | None = None

        if self.verbose:
            print(f"MockRealtimeDataProvider initialized with config: {self._symbols_config}")
            print(f"Initial prices: {self._current_prices}")

    def _generate_mock_price(self, symbol: str) -> float:
        """Generates a new mock price for the given symbol."""
        config = next(s_config for s_config in self._symbols_config if s_config['symbol'] == symbol)
        current_price = self._current_prices[symbol]
        volatility = config['volatility']

        change_percent = random.uniform(-volatility, volatility)
        new_price = current_price * (1 + change_percent)

        # Ensure price doesn't go to zero or negative (simple floor)
        new_price = max(0.01, new_price)

        self._current_prices[symbol] = new_price
        return new_price

    def _notify_subscribers(self, symbol: str, data_tick: DataTick) -> None:
        """Notifies all subscribers for a given symbol."""
        if symbol in self._subscribers:
            for callback in self._subscribers[symbol]:
                try:
                    callback(data_tick)
                except Exception as e:
                    print(f"Error in subscriber callback for {symbol}: {e}")

    def _tick_loop(self) -> None:
        """The main loop that generates ticks and notifies subscribers."""
        if self.verbose:
            print("MockRealtimeDataProvider: Tick loop started.")
        while self._running:
            current_time = time.time()
            for config in self._symbols_config:
                symbol = config['symbol']
                interval = config['interval_seconds']
                if current_time - self._last_update_times[symbol] >= interval:
                    new_price = self._generate_mock_price(symbol)
                    # Instantiate DataTick as a namedtuple
                    data_tick = DataTick(symbol=symbol, timestamp=current_time, price=new_price)
                    
                    # Log every generated tick if verbose
                    if self.verbose:
                        # Use attribute access for logging consistent with namedtuple
                        print(f"MockRealtimeDataProvider: Generated {data_tick.symbol} Tick: Price={data_tick.price:.2f}, Timestamp={time.ctime(data_tick.timestamp)}")
                    
                    # Notify subscribers and log if there are any
                    if symbol in self._subscribers and self._subscribers[symbol]:
                        if self.verbose:
                            print(f"MockRealtimeDataProvider: Notifying {len(self._subscribers[symbol])} subscribers for {symbol}.")
                        self._notify_subscribers(symbol, data_tick)
                    elif self.verbose: # If verbose and no subscribers for this tick's symbol
                        print(f"MockRealtimeDataProvider: No subscribers for {symbol} for this tick.")
                        
                    self._last_update_times[symbol] = current_time

            # Sleep for a short duration to prevent busy-waiting and allow graceful shutdown
            # This also determines the "granularity" of checking update intervals
            time.sleep(0.1)
        if self.verbose:
            print("MockRealtimeDataProvider: Tick loop stopped.")

    def subscribe(self, symbol: str, callback_function: Callable[[DataTick], None]) -> None:
        if symbol not in self._subscribers:
            print(f"Warning: Attempting to subscribe to an unconfigured symbol: {symbol}")
            self._subscribers[symbol] = [] 

        if callback_function not in self._subscribers[symbol]:
            self._subscribers[symbol].append(callback_function)
            if self.verbose:
                print(f"MockRealtimeDataProvider: '{symbol}' subscribed by {callback_function.__name__}")
        else:
            print(f"Warning: Callback {callback_function.__name__} already subscribed to '{symbol}'")

    def unsubscribe(self, symbol: str, callback_function: Callable[[DataTick], None]) -> None:
        if symbol in self._subscribers and callback_function in self._subscribers[symbol]:
            self._subscribers[symbol].remove(callback_function)
            if self.verbose:
                print(f"MockRealtimeDataProvider: '{symbol}' unsubscribed by {callback_function.__name__}")
        else:
            print(f"Warning: Callback {callback_function.__name__} not found for symbol '{symbol}' or symbol itself not found.")

    def start(self) -> None:
        if not self._running:
            self._running = True
            # Ensure last update times are initialized to allow immediate first tick for relevant symbols
            current_time = time.time()
            for config in self._symbols_config:
                 # Ensure the key exists before assigning
                if config['symbol'] not in self._last_update_times:
                    self._last_update_times[config['symbol']] = 0.0 # Initialize if not present
                self._last_update_times[config['symbol']] = current_time - config.get('interval_seconds', 1.0) 

            self._thread = threading.Thread(target=self._tick_loop, daemon=True)  # daemon=True for auto-exit
            self._thread.start()
            if self.verbose:
                print("MockRealtimeDataProvider: Started.")
        elif self.verbose:
            print("MockRealtimeDataProvider: Already running.")

    def stop(self) -> None:
        if self._running:
            self._running = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)  # Wait for the thread to finish
            if self.verbose:
                print("MockRealtimeDataProvider: Stopped.")
        elif self.verbose:
            print("MockRealtimeDataProvider: Already stopped.")

    def get_current_price(self, symbol: str) -> float | None:
        """Returns the last known price for a given symbol."""
        return self._current_prices.get(symbol)


if __name__ == '__main__':
    # Example Usage (for testing this module directly)
    print("Running MockRealtimeDataProvider example...")

    def handle_stock_data(data: DataTick):
        # Use attribute access due to namedtuple change
        print(f"HANDLER_STOCK: Received {data.symbol} price: {data.price:.2f} at {time.ctime(data.timestamp)}")

    def handle_crypto_data(data: DataTick):
        # Use attribute access due to namedtuple change
        print(f"HANDLER_CRYPTO: Received {data.symbol} price: {data.price:.2f} at {time.ctime(data.timestamp)}")

    mock_config: List[SymbolConfig] = [
        {'symbol': 'SIM_STOCK_A', 'initial_price': 10.00, 'volatility': 0.01, 'interval_seconds': 2.0},  # Slower updates
        {'symbol': 'SIM_CRYPTO_X', 'initial_price': 3000.00, 'volatility': 0.005, 'interval_seconds': 0.5}  # Faster updates
    ]

    provider = MockRealtimeDataProvider(symbols_config=mock_config, verbose=True)

    provider.subscribe('SIM_STOCK_A', handle_stock_data)
    provider.subscribe('SIM_CRYPTO_X', handle_crypto_data)

    # Test subscribing the same handler to multiple symbols or multiple handlers to one
    provider.subscribe('SIM_STOCK_A', handle_crypto_data)  # Crypto handler also gets stock A

    provider.start()

    try:
        # Keep the main thread alive to see the output for a while
        for i in range(10):  # Run for approx 10 * 1 seconds
            time.sleep(1)
            # Example of dynamic unsubscription/subscription if needed
            if i == 4:
                print("\n>>> Unsubscribing handle_stock_data from SIM_STOCK_A <<<\n")
                provider.unsubscribe('SIM_STOCK_A', handle_stock_data)
            if i == 7:
                print("\n>>> Re-subscribing handle_stock_data to SIM_STOCK_A <<<\n")
                provider.subscribe('SIM_STOCK_A', handle_stock_data)

    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        print("Stopping provider...")
        provider.stop()
        print("Example finished.") 
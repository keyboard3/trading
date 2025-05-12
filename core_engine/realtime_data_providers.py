import time
import threading
import yfinance as yf
from typing import List, Dict, Callable, Optional, Any
import collections

from .realtime_feed_base import RealtimeDataProviderBase
from .realtime_feed import DataTick # Assuming DataTick is defined here

# Placeholder for LogColors if you have a central logging utility
class LogColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class YahooFinanceDataProvider(RealtimeDataProviderBase):
    """
    A real-time data provider that fetches data from Yahoo Finance.
    Note: Yahoo Finance data is typically delayed (e.g., 15-20 minutes).
    This provider polls data at a specified interval.
    """

    def __init__(self, 
                 symbols: List[str], 
                 polling_interval_seconds: int = 60, 
                 verbose: bool = False):
        """
        Initialize the Yahoo Finance data provider.

        Args:
            symbols: A list of stock symbols to track (e.g., ['AAPL', 'MSFT']).
            polling_interval_seconds: How often to poll Yahoo Finance for new data.
                                      Be mindful of rate limits.
            verbose: If True, enables detailed logging.
        """
        self._symbols: List[str] = list(set(symbols)) # Ensure unique symbols
        self._polling_interval_seconds: int = polling_interval_seconds
        self.verbose: bool = verbose
        
        self._current_prices: Dict[str, float] = {}
        self._subscribers: Dict[str, List[Callable[[DataTick], None]]] = {
            symbol: [] for symbol in self._symbols
        }
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock() # For thread-safe access to shared resources

        if self.verbose:
            print(f"{LogColors.OKCYAN}YahooFinanceDataProvider initialized for symbols: {self._symbols} "
                  f"with polling interval: {self._polling_interval_seconds}s{LogColors.ENDC}")

    def _fetch_data_for_symbol(self, symbol: str) -> Optional[DataTick]:
        """
        Fetches the latest (delayed) data for a single symbol.
        Implement actual yfinance call here.
        """
        if self.verbose:
            print(f"{LogColors.OKBLUE}YahooFinanceDataProvider: Attempting to fetch data for {symbol}...{LogColors.ENDC}")
        try:
            ticker = yf.Ticker(symbol)
            # Option 1: Use info (might be less prone to immediate rate limits for single price)
            info = ticker.info
            current_price = info.get('regularMarketPrice') or info.get('currentPrice') # Fallback for different fields
            
            if current_price is None:
                 # Try 'previousClose' if market is closed or 'regularMarketPrice' isn't available
                current_price = info.get('previousClose')
            
            if current_price is not None:
                timestamp = info.get('regularMarketTime') # This is usually an epoch timestamp
                if isinstance(timestamp, str): # Sometimes it's a string, convert if so
                    # Attempt to parse, handle potential errors or different formats if necessary
                    try:
                        timestamp = int(timestamp)
                    except ValueError:
                         timestamp = time.time() # Fallback to current time
                elif not isinstance(timestamp, (int,float)):
                    timestamp = time.time() # Fallback if not int or float

                # Ensure timestamp is float for DataTick if it was int
                timestamp = float(timestamp)

                data_tick = DataTick(symbol=symbol, timestamp=timestamp, price=float(current_price))
                if self.verbose:
                    print(f"{LogColors.OKGREEN}YahooFinanceDataProvider: Fetched for {symbol}: Price={data_tick.price:.2f} at {time.ctime(data_tick.timestamp)}{LogColors.ENDC}")
                return data_tick
            else:
                if self.verbose:
                    print(f"{LogColors.WARNING}YahooFinanceDataProvider: Could not get 'regularMarketPrice', 'currentPrice', or 'previousClose' for {symbol} from ticker.info. Info dump: {info}{LogColors.ENDC}")
                return None

        except Exception as e:
            if self.verbose:
                print(f"{LogColors.FAIL}YahooFinanceDataProvider: Error fetching data for {symbol}: {e}{LogColors.ENDC}")
            # Consider more specific error handling for rate limits (e.g., HTTP 429) if possible
        return None

    def _polling_loop(self) -> None:
        if self.verbose:
            print(f"{LogColors.OKCYAN}YahooFinanceDataProvider: Polling loop started.{LogColors.ENDC}")
        
        while self._running:
            loop_start_time = time.time()
            for symbol in self._symbols:
                if not self._running:  # Check again in case stop() was called during the loop
                    break
                
                data_tick = self._fetch_data_for_symbol(symbol)
                
                if data_tick:
                    with self._lock:
                        self._current_prices[symbol] = data_tick.price
                        if symbol in self._subscribers:
                            for callback in self._subscribers[symbol]:
                                try:
                                    callback(data_tick)
                                except Exception as e:
                                    print(f"{LogColors.FAIL}YahooFinanceDataProvider: Error in subscriber callback for {symbol}: {e}{LogColors.ENDC}")
                
                # Small delay between individual symbol fetches to be nicer to the API
                if len(self._symbols) > 1 and self._running : # only sleep if there are more symbols and still running
                    time.sleep(max(0.1, self._polling_interval_seconds / (len(self._symbols) * 2) ))


            if not self._running:
                break

            # Calculate how long to sleep to maintain the polling interval
            elapsed_time = time.time() - loop_start_time
            sleep_duration = max(0, self._polling_interval_seconds - elapsed_time)
            
            if self.verbose:
                print(f"{LogColors.OKBLUE}YahooFinanceDataProvider: Polling loop cycle finished. Fetched for {len(self._symbols)} symbols. Elapsed: {elapsed_time:.2f}s. Sleeping for {sleep_duration:.2f}s.{LogColors.ENDC}")

            time.sleep(sleep_duration) # Main polling interval sleep

        if self.verbose:
            print(f"{LogColors.OKCYAN}YahooFinanceDataProvider: Polling loop stopped.{LogColors.ENDC}")

    # --- Interface methods from RealtimeDataProviderBase ---
    def subscribe(self, symbol: str, callback_function: Callable[[DataTick], None]) -> None:
        with self._lock:
            if symbol not in self._symbols:
                # Optionally, allow dynamic subscription to new symbols
                # self._symbols.append(symbol)
                # self._subscribers.setdefault(symbol, [])
                print(f"{LogColors.WARNING}YahooFinanceDataProvider: Attempting to subscribe to unconfigured symbol '{symbol}'. Ignoring.{LogColors.ENDC}")
                return

            if callback_function not in self._subscribers[symbol]:
                self._subscribers[symbol].append(callback_function)
                if self.verbose:
                    print(f"{LogColors.OKGREEN}YahooFinanceDataProvider: '{symbol}' subscribed by {callback_function.__name__}{LogColors.ENDC}")
            elif self.verbose:
                print(f"{LogColors.WARNING}YahooFinanceDataProvider: Callback {callback_function.__name__} already subscribed to '{symbol}'.{LogColors.ENDC}")

    def unsubscribe(self, symbol: str, callback_function: Callable[[DataTick], None]) -> None:
        with self._lock:
            if symbol in self._subscribers and callback_function in self._subscribers[symbol]:
                self._subscribers[symbol].remove(callback_function)
                if self.verbose:
                    print(f"{LogColors.OKGREEN}YahooFinanceDataProvider: '{symbol}' unsubscribed by {callback_function.__name__}{LogColors.ENDC}")
            elif self.verbose:
                print(f"{LogColors.WARNING}YahooFinanceDataProvider: Callback {callback_function.__name__} not found for symbol '{symbol}' or symbol itself not found.{LogColors.ENDC}")
    
    def start(self) -> None:
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._polling_loop, daemon=True)
            self._thread.start()
            if self.verbose:
                print(f"{LogColors.OKCYAN}YahooFinanceDataProvider: Started.{LogColors.ENDC}")
        elif self.verbose:
            print(f"{LogColors.OKBLUE}YahooFinanceDataProvider: Already running.{LogColors.ENDC}")

    def stop(self) -> None:
        if self._running:
            self._running = False
            if self._thread and self._thread.is_alive():
                if self.verbose:
                    print(f"{LogColors.OKCYAN}YahooFinanceDataProvider: Stopping thread...{LogColors.ENDC}")
                self._thread.join(timeout=self._polling_interval_seconds + 5) # Wait a bit longer than poll interval
                if self._thread.is_alive():
                     print(f"{LogColors.WARNING}YahooFinanceDataProvider: Thread did not terminate gracefully.{LogColors.ENDC}")
            if self.verbose:
                print(f"{LogColors.OKCYAN}YahooFinanceDataProvider: Stopped.{LogColors.ENDC}")
        elif self.verbose:
            print(f"{LogColors.OKBLUE}YahooFinanceDataProvider: Already stopped.{LogColors.ENDC}")

    def get_current_price(self, symbol: str) -> Optional[float]:
        with self._lock:
            price = self._current_prices.get(symbol)
        if price is None and self.verbose:
            print(f"{LogColors.WARNING}YahooFinanceDataProvider: Price for '{symbol}' not yet available in cache.{LogColors.ENDC}")
        return price

if __name__ == '__main__':
    print(f"{LogColors.HEADER}--- YahooFinanceDataProvider Test ---{LogColors.ENDC}")

    test_symbols = ['AAPL', 'MSFT', 'NVDA'] # Using common, active symbols
    # test_symbols = ['PQRXYZ'] # Test with a non-existent symbol

    def simple_handler_aapl(data_tick: DataTick):
        print(f"{LogColors.OKGREEN}HANDLER_AAPL: Received {data_tick.symbol} Price={data_tick.price:.2f} at {time.ctime(data_tick.timestamp)}{LogColors.ENDC}")

    def simple_handler_msft(data_tick: DataTick):
        print(f"{LogColors.OKGREEN}HANDLER_MSFT: Received {data_tick.symbol} Price={data_tick.price:.2f} at {time.ctime(data_tick.timestamp)}{LogColors.ENDC}")
    
    def generic_handler(data_tick: DataTick):
        print(f"{LogColors.OKCYAN}HANDLER_GENERIC: Received {data_tick.symbol} Price={data_tick.price:.2f} at {time.ctime(data_tick.timestamp)}{LogColors.ENDC}")

    # Initialize with a short polling interval for testing, but be careful with real usage
    # A 60-second interval is more realistic for not getting rate-limited too quickly.
    # For a very quick test, use a shorter interval but run for a very short time.
    provider = YahooFinanceDataProvider(symbols=test_symbols, polling_interval_seconds=15, verbose=True)
    
    provider.subscribe('AAPL', simple_handler_aapl)
    provider.subscribe('MSFT', simple_handler_msft)
    provider.subscribe('NVDA', generic_handler)
    # provider.subscribe('PQRXYZ', generic_handler) # Test subscribing to a bad symbol if it was configured

    provider.start()
    
    print(f"{LogColors.HEADER}Provider started. Running for a few polling cycles... (e.g., ~45-60 seconds){LogColors.ENDC}")
    
    try:
        # Let it run for a few cycles to see output
        for i in range(3): # Number of full polling intervals to observe
            time.sleep(provider._polling_interval_seconds + 2) # Sleep a bit longer than the interval
            # Example: Get current price on demand
            if 'MSFT' in test_symbols:
                 msft_price = provider.get_current_price('MSFT')
                 if msft_price:
                     print(f"{LogColors.BOLD}ON-DEMAND: Current MSFT price: {msft_price:.2f}{LogColors.ENDC}")
                 else:
                     print(f"{LogColors.WARNING}ON-DEMAND: MSFT price not available yet.{LogColors.ENDC}")
            
            if i == 1 and 'AAPL' in test_symbols: # After some cycles
                print(f'''{LogColors.HEADER}
>>> Unsubscribing simple_handler_aapl from AAPL <<<
{LogColors.ENDC}''')
                provider.unsubscribe('AAPL', simple_handler_aapl)


    except KeyboardInterrupt:
        print(f"{LogColors.WARNING}Test interrupted by user.{LogColors.ENDC}")
    finally:
        print(f"{LogColors.HEADER}Stopping provider...{LogColors.ENDC}")
        provider.stop()
        print(f"{LogColors.HEADER}--- YahooFinanceDataProvider Test Finished ---{LogColors.ENDC}") 
import time
from typing import List, Dict, Any, Callable

from .portfolio import MockPortfolio # Assuming MockPortfolio is in portfolio.py in the same directory
from .realtime_feed_base import RealtimeDataProviderBase # Correct: Base class is here
from .realtime_feed import DataTick # Correct: DataTick is defined in realtime_feed.py

# Define the structure for a signal event that the engine expects
SignalEvent = Dict[str, Any] # e.g., {'type': 'signal', 'symbol': str, 'timestamp': float, 'signal': str ('BUY','SELL','HOLD'), 'price': float}

# Define the structure for a trade record
TradeRecord = Dict[str, Any] # e.g., {'trade_id': str, 'symbol': str, 'timestamp': float, 'type': str ('BUY','SELL'), 'quantity': int, 'price': float, 'cost': float}

class MockTradingEngine:
    """
    Simulates trade execution based on signals and manages a portfolio.
    Initial version uses fixed trade quantity and market order execution.
    """
    def __init__(self, 
                 portfolio: MockPortfolio, 
                 # data_provider: RealtimeDataProviderBase, # data_provider might not be strictly needed if price comes with signal
                 fixed_trade_quantity: int = 100,
                 verbose: bool = False):
        """
        Args:
            portfolio: An instance of MockPortfolio.
            # data_provider: An instance of a data provider (e.g., MockRealtimeDataProvider).
            #                  Used to fetch current prices if not provided with the signal.
            #                  For now, we assume price comes with the signal.
            fixed_trade_quantity: The quantity of shares to trade for each BUY/SELL signal.
            verbose: If True, enables detailed logging from the engine.
        """
        self.portfolio: MockPortfolio = portfolio
        # self.data_provider: RealtimeDataProviderBase = data_provider
        self.fixed_trade_quantity: int = fixed_trade_quantity
        self.verbose: bool = verbose
        self.trade_log: List[TradeRecord] = []
        self._trade_id_counter: int = 0

        if self.verbose:
            print(f"MockTradingEngine initialized. Fixed trade quantity: {self.fixed_trade_quantity}")

    def _generate_trade_id(self) -> str:
        self._trade_id_counter += 1
        return f"TRADE_{self._trade_id_counter:05d}"

    def handle_signal_event(self, event: SignalEvent) -> None:
        """
        Processes a signal event from a strategy.
        Signal event should contain: {'symbol': str, 'timestamp': float, 'signal': str, 'price': float}
        The 'signal' field can be 'BUY', 'SELL', or 'HOLD'.
        'price' is the price at which the signal was generated / trade should be attempted.
        """
        if self.verbose:
            print(f"MockTradingEngine: Received signal event: {event}")

        signal_type = event.get('signal', '').upper()
        symbol = event.get('symbol')
        price = event.get('price')
        timestamp = event.get('timestamp', time.time())

        if not all([signal_type, symbol, price is not None]): # price can be 0, so check for None
            if self.verbose:
                print(f"MockTradingEngine: Received incomplete or invalid signal event: {event}. Skipping.")
            return

        if signal_type == 'HOLD':
            if self.verbose:
                print(f"MockTradingEngine: Received HOLD signal for {symbol} at {price:.2f} (Timestamp: {time.ctime(timestamp)}). No action taken.")
            return
        
        if signal_type not in ['BUY', 'SELL']:
            if self.verbose:
                print(f"MockTradingEngine: Received unknown signal type '{signal_type}' for {symbol}. Skipping event: {event}")
            return

        quantity_to_trade = self.fixed_trade_quantity
        trade_id = self._generate_trade_id()
        
        if self.verbose:
            print(f"MockTradingEngine: Processing signal. Attempting {signal_type} {quantity_to_trade} of {symbol} at price {price:.2f}, Timestamp: {time.ctime(timestamp)}")

        # Attempt to record the transaction with the portfolio
        transaction_successful = self.portfolio.record_transaction(
            symbol=symbol,
            transaction_type=signal_type, # BUY or SELL
            quantity=quantity_to_trade,
            price=price,
            timestamp=timestamp
        )

        if transaction_successful:
            cost_or_proceeds = quantity_to_trade * price
            trade_record: TradeRecord = {
                'trade_id': trade_id,
                'symbol': symbol,
                'timestamp': timestamp,
                'type': signal_type,
                'quantity': quantity_to_trade,
                'price': price,
                'total_value': cost_or_proceeds
            }
            self.trade_log.append(trade_record)
            if self.verbose:
                print(f"MockTradingEngine: {signal_type} successful for {symbol}. Trade ID: {trade_id}. Recorded: {trade_record}. Portfolio updated.")
        elif self.verbose:
            print(f"MockTradingEngine: {signal_type} FAILED for {symbol} (e.g., insufficient funds/shares). Event: {event}. See portfolio logs.")
            
    def get_trade_log(self) -> List[TradeRecord]:
        return self.trade_log


if __name__ == '__main__':
    print("\n--- MockTradingEngine Test ---")
    
    # 1. Setup a MockPortfolio
    initial_cash = 20000.00
    portfolio = MockPortfolio(initial_cash=initial_cash)
    
    # 2. Setup MockTradingEngine
    # For this standalone test, data_provider is not critical as price comes with signal
    engine = MockTradingEngine(portfolio=portfolio, fixed_trade_quantity=50, verbose=True)
    
    print(f"\nInitial Portfolio Cash: {portfolio.get_cash():.2f}")
    print(f"Initial Portfolio Holdings: {portfolio.get_holdings()}")

    # 3. Simulate some signal events
    ts = time.time()

    # Signal 1: BUY AAPL
    buy_signal_aapl: SignalEvent = {
        'symbol': 'AAPL',
        'timestamp': ts,
        'signal': 'BUY',
        'price': 150.00
    }
    engine.handle_signal_event(buy_signal_aapl)
    ts += 1 # Increment timestamp for next event

    # Signal 2: BUY MSFT (should succeed if enough cash)
    buy_signal_msft: SignalEvent = {
        'symbol': 'MSFT',
        'timestamp': ts,
        'signal': 'BUY',
        'price': 280.00 
    }
    engine.handle_signal_event(buy_signal_msft)
    ts += 1

    # Signal 3: HOLD AAPL (should do nothing but log if verbose)
    hold_signal_aapl: SignalEvent = {
        'symbol': 'AAPL',
        'timestamp': ts,
        'signal': 'HOLD',
        'price': 152.00 
    }
    engine.handle_signal_event(hold_signal_aapl)
    ts += 1

    # Signal 4: SELL AAPL (should succeed)
    sell_signal_aapl: SignalEvent = {
        'symbol': 'AAPL',
        'timestamp': ts,
        'signal': 'SELL',
        'price': 155.00 
    }
    engine.handle_signal_event(sell_signal_aapl)
    ts += 1

    # Signal 5: Attempt to BUY GOOG (might fail if fixed_trade_quantity * price > remaining cash)
    buy_signal_goog: SignalEvent = {
        'symbol': 'GOOG',
        'timestamp': ts,
        'signal': 'BUY',
        'price': 2200.00 
    }
    engine.handle_signal_event(buy_signal_goog)
    ts += 1
    
    # Signal 6: Attempt to SELL MSFT more than fixed quantity (should fail if initial buy was only fixed_trade_quantity)
    # For this, we need to know if the first MSFT buy was 50. If so, selling 50 is fine.
    # If fixed_trade_quantity was, say, 10 for MSFT, and we try to sell 50, it would use portfolio logic.
    # The engine itself doesn't track quantity beyond fixed_trade_quantity per transaction.
    # The portfolio.record_transaction handles if enough shares are present.
    sell_signal_msft_again: SignalEvent = {
        'symbol': 'MSFT', 
        'timestamp': ts, 
        'signal': 'SELL', 
        'price': 285.00
    }
    engine.handle_signal_event(sell_signal_msft_again)
    ts += 1

    print("\n--- Final State ---")
    print(f"Final Portfolio Cash: {portfolio.get_cash():.2f}")
    print(f"Final Portfolio Holdings: {portfolio.get_holdings()}")
    print("\nTrade Log:")
    for trade in engine.get_trade_log():
        print(trade)
        
    # Example of calculating final portfolio value if we had a way to get current prices
    # For the test, we can just use the last signal prices or make them up
    current_prices_for_calc = {
        'AAPL': sell_signal_aapl['price'], # Last traded price for AAPL
        'MSFT': sell_signal_msft_again['price'] if portfolio.get_position('MSFT') else 0, # Last traded for MSFT if still held
        'GOOG': buy_signal_goog['price'] if portfolio.get_position('GOOG') else 0
    }
    final_total_value = portfolio.get_total_portfolio_value(current_prices=current_prices_for_calc)
    print(f"\nEstimated Final Portfolio Value (using last known/trade prices): {final_total_value:.2f}")

    print("\n--- MockTradingEngine Test Finished ---") 
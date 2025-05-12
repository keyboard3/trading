import time
from typing import List, Dict, Any, Callable, Optional

from .portfolio import MockPortfolio # Assuming MockPortfolio is in portfolio.py in the same directory
from .realtime_feed_base import RealtimeDataProviderBase # Correct: Base class is here
from .realtime_feed import DataTick # Correct: DataTick is defined in realtime_feed.py
from . import risk_manager # Use `from . import risk_manager` for explicit relative import
from .risk_manager import RiskAlert # Import RiskAlert namedtuple

# Define the structure for a signal event that the engine expects
SignalEvent = Dict[str, Any] # e.g., {'type': 'signal', 'symbol': str, 'timestamp': float, 'signal': str ('BUY','SELL','HOLD'), 'price': float}

# Define the structure for a trade record
TradeRecord = Dict[str, Any] # e.g., {'trade_id': str, 'symbol': str, 'timestamp': float, 'type': str ('BUY','SELL'), 'quantity': int, 'price': float, 'cost': float}

class MockTradingEngine:
    """
    Simulates trade execution based on signals, manages a portfolio, and checks risks.
    """
    def __init__(self, 
                 portfolio: MockPortfolio, 
                 fixed_trade_quantity: int = 100,
                 risk_parameters: Optional[Dict[str, float]] = None, # Added risk_parameters
                 current_price_provider_callback: Optional[Callable[[str], Optional[float]]] = None, # For risk checks
                 verbose: bool = False):
        """
        Args:
            portfolio: An instance of MockPortfolio.
            fixed_trade_quantity: The quantity of shares to trade for each BUY/SELL signal.
            risk_parameters: Parameters for risk management.
            current_price_provider_callback: Callback function to get current prices.
            verbose: If True, enables detailed logging from the engine.
        """
        self.portfolio: MockPortfolio = portfolio
        self.fixed_trade_quantity: int = fixed_trade_quantity
        self.verbose: bool = verbose
        self.trade_log: List[TradeRecord] = []
        self._trade_id_counter: int = 0
        self.active_risk_alerts: List[RiskAlert] = [] # To store current risk alerts
        
        # Store risk parameters, provide defaults if None for safety, though they should be passed from API
        self.risk_parameters = risk_parameters if risk_parameters is not None else {
            'stop_loss_pct': 0.10, 
            'max_pos_pct': 0.25, 
            'max_dd_pct': 0.15
        }
        self.current_price_provider_callback = current_price_provider_callback

        if self.verbose:
            print(f"MockTradingEngine initialized. Fixed trade quantity: {self.fixed_trade_quantity}. Risk Params: {self.risk_parameters}")

    def _generate_trade_id(self) -> str:
        self._trade_id_counter += 1
        return f"TRADE_{self._trade_id_counter:05d}"

    def _perform_risk_evaluation(self, trade_context: Optional[Dict[str, Any]] = None):
        """Helper to perform risk evaluation and update active_risk_alerts."""
        if not self.current_price_provider_callback:
            if self.verbose: print("MockTradingEngine: Risk evaluation skipped - no current price provider callback.")
            return

        portfolio_state = {
            'holdings_details': self.portfolio.get_holdings_with_details(self.current_price_provider_callback),
            'total_value': self.portfolio.get_total_portfolio_value(self.current_price_provider_callback),
            'peak_value': self.portfolio.get_peak_portfolio_value()
        }
        
        # Clear previous alerts for this cycle (or manage them more sophisticatedly if needed)
        # For now, we refresh alerts on each evaluation to reflect current state.
        # In a real system, alerts might persist until acknowledged or conditions change.
        self.active_risk_alerts.clear()
        
        new_alerts = risk_manager.evaluate_all_risks(
            portfolio_state=portfolio_state,
            risk_params=self.risk_parameters,
            trade_context=trade_context, # For pre-trade checks
            verbose=self.verbose
        )
        self.active_risk_alerts.extend(new_alerts)

        if self.verbose and self.active_risk_alerts:
            print(f"MockTradingEngine: Active Risk Alerts after evaluation ({'Pre-trade for ' + trade_context['symbol'] if trade_context else 'Post-update'}):")
            for alert in self.active_risk_alerts:
                print(f"  - {alert}")

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

        # --- Post-update/General Risk Check (before processing new signal actions) ---
        # This evaluates risks based on the latest market data before any new trade action
        # We call this at the start of handling a new signal, assuming prices might have changed
        # since the last signal or the portfolio state might have been affected.
        if self.current_price_provider_callback:
             # Important: The `price` in the signal event is the *signal price*.
             # For general risk evaluation of *existing* positions, we need their *latest market prices*.
             # This is handled by `_perform_risk_evaluation` using `self.current_price_provider_callback`.
            self._perform_risk_evaluation() 
        else:
            if self.verbose: print("MockTradingEngine: Skipping initial risk evaluation as no price callback is set.")

        if signal_type == 'HOLD':
            if self.verbose:
                print(f"MockTradingEngine: Received HOLD signal for {symbol} at {price:.2f} (Timestamp: {time.ctime(timestamp)}). No action taken.")
            return
        
        if signal_type not in ['BUY', 'SELL']:
            if self.verbose:
                print(f"MockTradingEngine: Received unknown signal type '{signal_type}' for {symbol}. Skipping event: {event}")
            return

        quantity_to_trade = self.fixed_trade_quantity
        
        # --- Pre-Trade Risk Check for BUY signals (Max Position Size) ---
        if signal_type == 'BUY' and self.current_price_provider_callback:
            current_position_details = self.portfolio.get_position(symbol)
            current_quantity = current_position_details['quantity'] if current_position_details else 0
            
            potential_new_quantity = current_quantity + quantity_to_trade
            # Use the signal's price for calculating potential market value of the *new* trade
            potential_market_value_of_position = potential_new_quantity * price 
            
            trade_context_for_buy = {
                'symbol': symbol,
                'potential_market_value_after_trade': potential_market_value_of_position
            }
            self._perform_risk_evaluation(trade_context=trade_context_for_buy)
            
            # Check if the pre-trade check specifically added a MAX_POSITION_SIZE_PRE_TRADE alert for this symbol
            if any(a.alert_type == 'MAX_POSITION_SIZE_PRE_TRADE' and a.symbol == symbol for a in self.active_risk_alerts):
                if self.verbose:
                    print(f"MockTradingEngine: PRE-TRADE RISK. BUY for {symbol} blocked due to Max Position Size alert.")
                # Potentially log this blocked trade or notify strategy if that mechanism exists
                return # Do not proceed with the trade

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
            
            # --- Post-Transaction Risk Re-evaluation ---
            # After a successful trade, re-evaluate all risks with the new portfolio state.
            # This will catch stop-loss on newly acquired positions if price was bad,
            # or confirm max position size with actual portfolio data, and check drawdown.
            if self.current_price_provider_callback:
                self._perform_risk_evaluation()
            else:
                 if self.verbose: print("MockTradingEngine: Skipping post-transaction risk evaluation - no price callback.")

        elif self.verbose:
            print(f"MockTradingEngine: {signal_type} FAILED for {symbol} (e.g., insufficient funds/shares). Event: {event}. See portfolio logs.")
            
    def get_trade_log(self) -> List[TradeRecord]:
        return self.trade_log
    
    def get_active_risk_alerts(self) -> List[RiskAlert]: # New method to get alerts
        return self.active_risk_alerts.copy() # Return a copy


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
import time
from typing import List, Dict, Any, Callable, Optional

from .portfolio import MockPortfolio # Assuming MockPortfolio is in portfolio.py in the same directory
from .realtime_feed_base import RealtimeDataProviderBase # Correct: Base class is here
from .realtime_feed import DataTick # Correct: DataTick is defined in realtime_feed.py
from . import risk_manager # Use `from . import risk_manager` for explicit relative import
from .risk_manager import RiskAlert # Import RiskAlert namedtuple

# Import LogColors
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
try:
    from backend.logger_utils import LogColors
except ImportError:
    print("Critical Error: Could not import LogColors from backend.logger_utils. Colored logs will not be available in TradingEngine.")
    class LogColors:
        HEADER = ''
        OKBLUE = ''
        OKCYAN = ''
        OKGREEN = ''
        WARNING = ''
        FAIL = ''
        ENDC = ''
        BOLD = ''
        UNDERLINE = ''

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
            print(f"{LogColors.OKCYAN}MockTradingEngine initialized. Fixed trade quantity: {self.fixed_trade_quantity}. Risk Params: {self.risk_parameters}{LogColors.ENDC}")

    def _generate_trade_id(self) -> str:
        self._trade_id_counter += 1
        return f"TRADE_{self._trade_id_counter:05d}"

    def _perform_risk_evaluation(self, trade_context: Optional[Dict[str, Any]] = None):
        """Helper to perform risk evaluation and update active_risk_alerts."""
        if not self.current_price_provider_callback:
            if self.verbose: print(f"{LogColors.WARNING}MockTradingEngine: Risk evaluation skipped - no current price provider callback.{LogColors.ENDC}")
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
            context_msg = f"Pre-trade for {trade_context['symbol']}" if trade_context else "Post-update"
            print(f"{LogColors.WARNING}MockTradingEngine: Active Risk Alerts after evaluation ({context_msg}):{LogColors.ENDC}")
            for alert in self.active_risk_alerts:
                print(f"{LogColors.WARNING}  - {alert}{LogColors.ENDC}")

    def handle_signal_event(self, event: SignalEvent) -> None:
        """
        Processes a signal event from a strategy.
        Signal event should contain: {'symbol': str, 'timestamp': float, 'signal': str, 'price': float}
        The 'signal' field can be 'BUY', 'SELL', or 'HOLD'.
        'price' is the price at which the signal was generated / trade should be attempted.
        """
        if self.verbose:
            print(f"{LogColors.OKBLUE}MockTradingEngine: Received signal event: {event}{LogColors.ENDC}")

        signal_type = event.get('signal', '').upper()
        symbol = event.get('symbol')
        price = event.get('price')
        timestamp = event.get('timestamp', time.time())

        if not all([signal_type, symbol, price is not None]): # price can be 0, so check for None
            if self.verbose:
                print(f"{LogColors.FAIL}MockTradingEngine: Received incomplete or invalid signal event: {event}. Skipping.{LogColors.ENDC}")
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
            if self.verbose: print(f"{LogColors.WARNING}MockTradingEngine: Skipping initial risk evaluation as no price callback is set.{LogColors.ENDC}")

        if signal_type == 'HOLD':
            if self.verbose:
                print(f"{LogColors.OKBLUE}MockTradingEngine: Received HOLD signal for {symbol} at {price:.2f} (Timestamp: {time.ctime(timestamp)}). No action taken.{LogColors.ENDC}")
            return
        
        if signal_type not in ['BUY', 'SELL']:
            if self.verbose:
                print(f"{LogColors.FAIL}MockTradingEngine: Received unknown signal type '{signal_type}' for {symbol}. Skipping event: {event}{LogColors.ENDC}")
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
            if self.verbose: print(f"{LogColors.OKCYAN}MockTradingEngine: Performing PRE-TRADE risk check for BUY {symbol}...{LogColors.ENDC}")
            self._perform_risk_evaluation(trade_context=trade_context_for_buy)
            
            # Check if the pre-trade check specifically added a MAX_POSITION_SIZE_PRE_TRADE alert for this symbol
            if any(a.alert_type == 'MAX_POSITION_SIZE_PRE_TRADE' and a.symbol == symbol for a in self.active_risk_alerts):
                if self.verbose:
                    print(f"{LogColors.FAIL}MockTradingEngine: PRE-TRADE RISK. BUY for {symbol} blocked due to Max Position Size alert.{LogColors.ENDC}")
                # Potentially log this blocked trade or notify strategy if that mechanism exists
                return # Do not proceed with the trade

        trade_id = self._generate_trade_id()
        
        if self.verbose:
            print(f"{LogColors.OKCYAN}MockTradingEngine: Processing signal. Attempting {signal_type} {quantity_to_trade} of {symbol} at price {price:.2f}, Timestamp: {time.ctime(timestamp)}{LogColors.ENDC}")

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
                print(f"{LogColors.OKGREEN}MockTradingEngine: {signal_type} successful for {symbol}. Trade ID: {trade_id}. Recorded: {trade_record}. Portfolio updated.{LogColors.ENDC}")
            
            # --- Post-Transaction Risk Re-evaluation ---
            # After a successful trade, re-evaluate all risks with the new portfolio state.
            # This will catch stop-loss on newly acquired positions if price was bad,
            # or confirm max position size with actual portfolio data, and check drawdown.
            if self.current_price_provider_callback:
                if self.verbose: print(f"{LogColors.OKCYAN}MockTradingEngine: Performing POST-TRADE risk evaluation...{LogColors.ENDC}")
                self._perform_risk_evaluation()
            else:
                 if self.verbose: print(f"{LogColors.WARNING}MockTradingEngine: Skipping post-transaction risk evaluation - no price callback.{LogColors.ENDC}")

        elif self.verbose:
            print(f"{LogColors.FAIL}MockTradingEngine: {signal_type} FAILED for {symbol} (e.g., insufficient funds/shares). Event: {event}. See portfolio logs.{LogColors.ENDC}")
            
    def get_trade_log(self) -> List[TradeRecord]:
        return self.trade_log
    
    def get_active_risk_alerts(self) -> List[RiskAlert]: # New method to get alerts
        return self.active_risk_alerts.copy() # Return a copy


if __name__ == '__main__':
    print(f"{LogColors.HEADER}\n--- MockTradingEngine Test ---{LogColors.ENDC}")
    
    initial_cash = 30000.00 # Increased initial cash to allow more trades for testing risk
    portfolio = MockPortfolio(initial_cash=initial_cash, verbose=True)
    
    # Mock current price provider for risk evaluation tests
    mock_market_prices = {
        'AAPL': 150.0, 
        'MSFT': 280.0, 
        'GOOG': 2000.0,
        'TSLA': 100.0 # Added for another position
    }
    def mock_price_provider(symbol: str) -> Optional[float]:
        price = mock_market_prices.get(symbol)
        # Ensure portfolio's verbose flag is accessible or pass engine's verbose
        # For simplicity here, let's assume we want these logs if engine is verbose.
        # if portfolio.verbose: 
        print(f"{LogColors.OKBLUE}MockPriceProvider: Request for {symbol}, returning {price}{LogColors.ENDC}")
        return price

    # Risk parameters for testing - make them somewhat restrictive to trigger easily
    test_risk_params = {
        'stop_loss_pct': 0.05,      # 5% stop loss from avg cost
        'max_pos_pct': 0.40,        # Max 40% of portfolio in one asset 
        'max_dd_pct': 0.10           # Max 10% drawdown from peak portfolio value
    }

    engine = MockTradingEngine(
        portfolio=portfolio, 
        fixed_trade_quantity=50, # Default trade quantity
        risk_parameters=test_risk_params, 
        current_price_provider_callback=mock_price_provider, # PROVIDE THE CALLBACK
        verbose=True
    )
    
    print(f"{LogColors.OKCYAN}\nInitial Portfolio Cash: {portfolio.get_cash():.2f}{LogColors.ENDC}")
    print(f"{LogColors.OKCYAN}Initial Portfolio Holdings: {portfolio.get_holdings()}{LogColors.ENDC}")
    portfolio.peak_portfolio_value = initial_cash # Explicitly set initial peak

    ts = time.time()

    # --- Test Sequence --- 

    print(f"{LogColors.HEADER}\nSignal 1: BUY AAPL (50 * $150 = $7500). Cash: 22500. Total: 30000. Peak: 30000{LogColors.ENDC}")
    # AAPL is 7500 / 30000 = 25% (OK, limit 40%)
    buy_signal_aapl: SignalEvent = { 'symbol': 'AAPL', 'timestamp': ts, 'signal': 'BUY', 'price': 150.00 }
    engine.handle_signal_event(buy_signal_aapl)
    ts += 1

    print(f"{LogColors.HEADER}\nSignal 2: BUY TSLA (50 * $100 = $5000). Cash: 17500. Holdings: AAPL 7500, TSLA 5000. Total: 30000. Peak: 30000{LogColors.ENDC}")
    # TSLA is 5000 / 30000 = 16.67% (OK)
    # AAPL is 7500 / 30000 = 25% (OK)
    buy_signal_tsla: SignalEvent = { 'symbol': 'TSLA', 'timestamp': ts, 'signal': 'BUY', 'price': 100.00 }
    engine.handle_signal_event(buy_signal_tsla)
    ts += 1

    print(f"{LogColors.HEADER}\nSignal 3: AAPL price drops to $140 (Stop-Loss Test). Loss: (150-140)/150 = 6.67% > 5%{LogColors.ENDC}")
    mock_market_prices['AAPL'] = 140.0
    # Holdings: AAPL 50*140=7000, TSLA 50*100=5000. Cash 17500. Total: 7000+5000+17500 = 29500.
    # Peak 30000. Drawdown (30000-29500)/30000 = 500/30000 = 1.67% (OK, limit 10%)
    hold_signal_aapl_sl: SignalEvent = { 'symbol': 'AAPL', 'timestamp': ts, 'signal': 'HOLD', 'price': 140.0 } # Price in HOLD is for context
    engine.handle_signal_event(hold_signal_aapl_sl)
    ts += 1
    assert any(a.alert_type == 'STOP_LOSS_PER_POSITION' and a.symbol == 'AAPL' for a in engine.get_active_risk_alerts()), "Stop loss for AAPL should be triggered"
    print(f"{LogColors.OKGREEN}Stop-loss for AAPL successfully triggered.{LogColors.ENDC}")

    print(f"{LogColors.HEADER}\nSignal 4: Attempt to BUY MSFT (50 * $280 = $14000). Cash needed. Available: 17500. Will pass cash check.{LogColors.ENDC}")
    print(f"{LogColors.HEADER}PRE-TRADE CHECK: MSFT would be $14000. Portfolio total $29500 (before this trade). $14000/$29500 = 47.4% > 40% limit.{LogColors.ENDC}")
    # This BUY should be BLOCKED by pre-trade max position size check.
    buy_signal_msft: SignalEvent = { 'symbol': 'MSFT', 'timestamp': ts, 'signal': 'BUY', 'price': 280.00 }
    trades_before_msft_buy = len(engine.get_trade_log())
    engine.handle_signal_event(buy_signal_msft)
    ts += 1
    assert any(a.alert_type == 'MAX_POSITION_SIZE_PRE_TRADE' and a.symbol == 'MSFT' for a in engine.get_active_risk_alerts()), "Max Position Size (PRE-TRADE) for MSFT should be triggered"
    assert len(engine.get_trade_log()) == trades_before_msft_buy, "MSFT trade should have been BLOCKED"
    print(f"{LogColors.OKGREEN}Max Position Size (PRE-TRADE) for MSFT successfully triggered and trade BLOCKED.{LogColors.ENDC}")

    print(f"{LogColors.HEADER}\nSignal 5: TSLA price drops to $80 (Drawdown Test). AAPL still at $140.{LogColors.ENDC}")
    mock_market_prices['TSLA'] = 80.0
    # Holdings: AAPL 50*140=7000, TSLA 50*80=4000. Cash 17500. Total: 7000+4000+17500 = 28500.
    # Peak 30000. Drawdown (30000-28500)/30000 = 1500/30000 = 5% (OK, limit 10%)
    # Let's make it trigger: Need total value to be < 27000 (10% of 30k peak is 3k drop)
    # Current total is 28500. Need another 1501 drop. Let AAPL also drop more.
    mock_market_prices['AAPL'] = 110.0 # AAPL: 50*110=5500. TSLA: 50*80=4000. Cash 17500. Total: 5500+4000+17500 = 27000.
    # Drawdown (30000-27000)/30000 = 3000/30000 = 10%. This should trigger.
    # Actually, if it's *exactly* 10%, the check is `drawdown > limit`, so it won't trigger. Let's make it slightly more.
    mock_market_prices['AAPL'] = 109.0 # AAPL: 50*109=5450. TSLA: 50*80=4000. Cash 17500. Total: 5450+4000+17500 = 26950.
    # Drawdown (30000-26950)/30000 = 3050/30000 = 10.16% > 10%. This WILL trigger.
    hold_signal_dd: SignalEvent = { 'symbol': 'TSLA', 'timestamp': ts, 'signal': 'HOLD', 'price': 80.0 }
    engine.handle_signal_event(hold_signal_dd)
    ts += 1
    assert any(a.alert_type == 'MAX_ACCOUNT_DRAWDOWN' for a in engine.get_active_risk_alerts()), "Max Account Drawdown should be triggered"
    # Also, AAPL stop loss might trigger again if its avg cost is still 150 and price is 109: (150-109)/150 = 41/150 = 27% loss.
    assert any(a.alert_type == 'STOP_LOSS_PER_POSITION' and a.symbol == 'AAPL' for a in engine.get_active_risk_alerts()), "Stop loss for AAPL should be re-triggered or still active"
    print(f"{LogColors.OKGREEN}Max Account Drawdown (and AAPL SL) successfully triggered.{LogColors.ENDC}")

    print(f"{LogColors.HEADER}\nSignal 6: Sell all AAPL (50 * $109 = $5995).{LogColors.ENDC}")
    # Before: Cash 17500. Holdings: AAPL 5450, TSLA 4000. Total 26950.
    # After: Cash 17500+5995=23495. Holdings: TSLA 4000. Total 27495.
    # Peak 30000. Drawdown (30000-27495)/30000 = 2505/30000 = 8.35% (OK)
    sell_signal_aapl: SignalEvent = { 'symbol': 'AAPL', 'timestamp': ts, 'signal': 'SELL', 'price': 109.00 }
    engine.handle_signal_event(sell_signal_aapl)
    ts += 1

    print(f"{LogColors.HEADER}\nSignal 7: Sell all TSLA (50 * $80 = $4000).{LogColors.ENDC}")
    # Before: Cash 23495. Holdings: TSLA 4000. Total 27495.
    # After: Cash 23495+4000=27495. Holdings: {}. Total 27495.
    # Peak 30000. Drawdown 8.35% (OK)
    sell_signal_tsla: SignalEvent = { 'symbol': 'TSLA', 'timestamp': ts, 'signal': 'SELL', 'price': 80.00 }
    engine.handle_signal_event(sell_signal_tsla)
    ts += 1

    print(f"{LogColors.HEADER}\n--- Final State ---{LogColors.ENDC}")
    print(f"{LogColors.OKCYAN}Final Portfolio Cash: {portfolio.get_cash():.2f}{LogColors.ENDC}")
    print(f"{LogColors.OKCYAN}Final Portfolio Holdings: {portfolio.get_holdings()}{LogColors.ENDC}")
    print(f"{LogColors.OKCYAN}Final Trade Log: {engine.get_trade_log()}{LogColors.ENDC}")
    # After selling all, risk alerts might clear if they were position specific and positions are gone,
    # or Max DD might persist if value hasn't recovered above threshold.
    # Let's perform one last risk eval manually by sending a HOLD for a non-existent symbol or similar
    print(f"{LogColors.OKCYAN}Performing final risk evaluation...{LogColors.ENDC}")
    final_eval_event: SignalEvent = {'symbol': 'DUMMY', 'timestamp':ts, 'signal':'HOLD', 'price':0}
    engine.handle_signal_event(final_eval_event)
    print(f"{LogColors.WARNING}Final Active Risk Alerts: {engine.get_active_risk_alerts()}{LogColors.ENDC}")

    print(f"{LogColors.HEADER}\n--- MockTradingEngine Test Finished ---{LogColors.ENDC}") 
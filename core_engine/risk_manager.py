from typing import List, Dict, Any, Optional, Callable
import time
import collections
import sys
import os

# Attempt to import LogColors from the new backend.logger_utils
# This might require adjusting PYTHONPATH if core_engine is not structured as a sub-package of backend
# or if they are distinct top-level packages.
# For a typical structure where backend and core_engine are top-level or under a common root recognised by Python:
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
try:
    from backend.logger_utils import LogColors
except ImportError:
    print("Critical Error: Could not import LogColors from backend.logger_utils. Colored logs will not be available in RiskManager.")
    # Define a fallback LogColors class if import fails, so the rest of the code doesn't break
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

# Assuming MockPortfolio is in a sibling file or accessible via PYTHONPATH
# from .portfolio import MockPortfolio # Example for relative import if in same package
# For now, to avoid circular dependencies or complex pathing, we might pass portfolio state directly

# --- Risk Alert Definition ---
RiskAlert = collections.namedtuple('RiskAlert', ['alert_type', 'symbol', 'message', 'timestamp'])

# --- Risk Parameters (passed in or defined globally if static) ---
# These would typically be configured elsewhere and passed into the functions
# For example purposes, they are shown here as potential arguments or could be fetched from a config object

def check_stop_loss_per_position(
    portfolio_holdings_with_details: List[Dict[str, Any]],
    risk_max_unrealized_loss_percentage: float,
    verbose: bool = False
) -> List[RiskAlert]:
    """
    Checks if any position has an unrealized loss exceeding the_max_unrealized_loss_percentage of its average cost.
    portfolio_holdings_with_details: List of dicts, each from MockPortfolio.get_holdings_with_details()
    """
    alerts = []
    for holding in portfolio_holdings_with_details:
        symbol = holding['symbol']
        avg_cost = holding['average_cost_price']
        current_price = holding.get('current_price') # Might be None if price not available
        quantity = holding['quantity']

        if quantity == 0 or avg_cost == 0: # Should not happen for active holdings with cost
            continue
        
        if current_price is not None and current_price > 0:
            unrealized_pnl_per_share = current_price - avg_cost
            if unrealized_pnl_per_share < 0: # It's a loss
                loss_percentage = abs(unrealized_pnl_per_share) / avg_cost
                if loss_percentage >= risk_max_unrealized_loss_percentage:
                    message = (
                        f"Stop-Loss triggered for {symbol}. "
                        f"Loss: {loss_percentage*100:.2f}% (Limit: {risk_max_unrealized_loss_percentage*100:.2f}%). "
                        f"Avg Cost: {avg_cost:.2f}, Current Price: {current_price:.2f}, Qty: {quantity}."
                    )
                    alerts.append(RiskAlert('STOP_LOSS_PER_POSITION', symbol, message, time.time()))
                    if verbose: print(f"{LogColors.WARNING}RiskManager: {message}{LogColors.ENDC}")
    return alerts

def check_max_position_size(
    portfolio_holdings_with_details: List[Dict[str, Any]],
    total_portfolio_value: float,
    risk_max_position_size_percentage: float,
    symbol_being_traded: Optional[str] = None, # For pre-trade check: the symbol we are about to buy/increase
    potential_new_market_value: Optional[float] = None, # For pre-trade check: the new market value of the position after the trade
    verbose: bool = False
) -> List[RiskAlert]:
    """
    Checks if any single position's market value (or potential market value for pre-trade check)
    exceeds risk_max_position_size_percentage of the total_portfolio_value.
    """
    alerts = []
    if total_portfolio_value == 0: # Avoid division by zero
        if verbose: print(f"{LogColors.WARNING}RiskManager: Total portfolio value is 0, cannot check max position size.{LogColors.ENDC}")
        return alerts

    # Check existing positions (post-trade or general check)
    for holding in portfolio_holdings_with_details:
        symbol = holding['symbol']
        market_value = holding.get('market_value', 0.0)
        if market_value > 0: # Only consider positions with positive market value
            position_percentage = market_value / total_portfolio_value
            if position_percentage > risk_max_position_size_percentage:
                message = (
                    f"Max Position Size triggered for {symbol}. "
                    f"Holding: {position_percentage*100:.2f}% (Limit: {risk_max_position_size_percentage*100:.2f}%). "
                    f"Market Value: {market_value:.2f}, Portfolio Value: {total_portfolio_value:.2f}."
                )
                alerts.append(RiskAlert('MAX_POSITION_SIZE', symbol, message, time.time()))
                if verbose: print(f"{LogColors.WARNING}RiskManager: {message}{LogColors.ENDC}")

    # Pre-trade check for the specific symbol being traded if provided
    if symbol_being_traded and potential_new_market_value is not None:
        if potential_new_market_value > 0:
            potential_percentage = potential_new_market_value / total_portfolio_value
            if potential_percentage > risk_max_position_size_percentage:
                # Check if this alert is already added for this symbol to avoid duplicates if post-trade check also caught it
                # This simple check might not be perfect if post-trade values are very different.
                # For a strict pre-trade, the post-trade loop for this symbol might be skipped or handled differently.
                is_already_alerted = any(a.symbol == symbol_being_traded and a.alert_type == 'MAX_POSITION_SIZE' for a in alerts)
                if not is_already_alerted:
                    message = (
                        f"PRE-TRADE Max Position Size triggered for {symbol_being_traded}. "
                        f"Potential Holding: {potential_percentage*100:.2f}% (Limit: {risk_max_position_size_percentage*100:.2f}%). "
                        f"Potential Market Value: {potential_new_market_value:.2f}, Portfolio Value: {total_portfolio_value:.2f}."
                    )
                    alerts.append(RiskAlert('MAX_POSITION_SIZE_PRE_TRADE', symbol_being_traded, message, time.time()))
                    if verbose: print(f"{LogColors.WARNING}RiskManager: {message}{LogColors.ENDC}")
    return alerts

def check_max_account_drawdown(
    current_total_portfolio_value: float,
    peak_portfolio_value: float,
    risk_max_account_drawdown_percentage: float,
    verbose: bool = False
) -> List[RiskAlert]:
    """
    Checks if the current_total_portfolio_value has dropped from peak_portfolio_value 
    by more than risk_max_account_drawdown_percentage.
    """
    alerts = []
    if peak_portfolio_value <= 0: # Avoid issues if peak is zero or negative (e.g. initial error)
        if verbose: print(f"{LogColors.WARNING}RiskManager: Peak portfolio value is non-positive ({peak_portfolio_value}), cannot check max account drawdown.{LogColors.ENDC}")
        return alerts

    drawdown = (peak_portfolio_value - current_total_portfolio_value) / peak_portfolio_value
    if drawdown > risk_max_account_drawdown_percentage:
        message = (
            f"Max Account Drawdown triggered. "
            f"Current Drawdown: {drawdown*100:.2f}% (Limit: {risk_max_account_drawdown_percentage*100:.2f}%). "
            f"Peak Value: {peak_portfolio_value:.2f}, Current Value: {current_total_portfolio_value:.2f}."
        )
        alerts.append(RiskAlert('MAX_ACCOUNT_DRAWDOWN', None, message, time.time()))
        if verbose: print(f"{LogColors.WARNING}RiskManager: {message}{LogColors.ENDC}")
    return alerts


def evaluate_all_risks(
    portfolio_state: Dict[str, Any], # Expects keys like 'holdings_details', 'total_value', 'peak_value'
    risk_params: Dict[str, float],    # Expects keys like 'stop_loss_pct', 'max_pos_pct', 'max_dd_pct'
    # For pre-trade specific checks:
    trade_context: Optional[Dict[str, Any]] = None, # e.g., {'symbol': 'MSFT', 'potential_market_value_after_trade': 12000.0 }
    verbose: bool = False
) -> List[RiskAlert]:
    """
    Evaluates all configured risk rules based on the current portfolio state and risk parameters.
    Can also perform pre-trade checks if trade_context is provided.
    """
    all_alerts = []
    
    # Post-trade / general checks
    all_alerts.extend(check_stop_loss_per_position(
        portfolio_holdings_with_details=portfolio_state.get('holdings_details', []),
        risk_max_unrealized_loss_percentage=risk_params['stop_loss_pct'],
        verbose=verbose
    ))
    
    # For max position size, we need to differentiate pre-trade from post-trade/general check slightly
    symbol_being_traded = None
    potential_new_market_value = None
    if trade_context:
        symbol_being_traded = trade_context.get('symbol')
        potential_new_market_value = trade_context.get('potential_market_value_after_trade')

    all_alerts.extend(check_max_position_size(
        portfolio_holdings_with_details=portfolio_state.get('holdings_details', []),
        total_portfolio_value=portfolio_state['total_value'],
        risk_max_position_size_percentage=risk_params['max_pos_pct'],
        symbol_being_traded=symbol_being_traded, # Pass context for pre-trade
        potential_new_market_value=potential_new_market_value, # Pass context for pre-trade
        verbose=verbose
    ))
    
    all_alerts.extend(check_max_account_drawdown(
        current_total_portfolio_value=portfolio_state['total_value'],
        peak_portfolio_value=portfolio_state['peak_value'],
        risk_max_account_drawdown_percentage=risk_params['max_dd_pct'],
        verbose=verbose
    ))
    
    # Deduplicate alerts (simple deduplication based on type, symbol, and first few chars of message if needed)
    # This is a basic way; more sophisticated alert management might be needed for frequent checks.
    # For now, assuming evaluate_all_risks is not called so frequently that this becomes a major issue.
    # If alerts can persist across calls, this deduplication should happen at a higher level.
    # For this function, it just returns all found alerts from this specific evaluation.
    
    return all_alerts


if __name__ == '__main__':
    print("--- RiskManager Test ---")
    
    # Mock data for testing
    mock_holdings_details_loss = [
        {'symbol': 'AAPL', 'average_cost_price': 150.0, 'current_price': 130.0, 'quantity': 10, 'market_value': 1300.0},
        {'symbol': 'MSFT', 'average_cost_price': 200.0, 'current_price': 210.0, 'quantity': 5, 'market_value': 1050.0}
    ]
    mock_holdings_details_pos_size = [
        {'symbol': 'GOOG', 'average_cost_price': 2000.0, 'current_price': 2100.0, 'quantity': 10, 'market_value': 21000.0}, # 70% of 30k
        {'symbol': 'TSLA', 'average_cost_price': 700.0, 'current_price': 750.0, 'quantity': 5, 'market_value': 3750.0}
    ]

    risk_parameters = {
        'stop_loss_pct': 0.10,  # 10%
        'max_pos_pct': 0.25,    # 25%
        'max_dd_pct': 0.15      # 15%
    }

    # Test Stop Loss
    print("\nTesting Stop Loss:")
    portfolio_state_sl = {
        'holdings_details': mock_holdings_details_loss,
        'total_value': 2350.0, # Not directly used by stop loss check itself beyond context
        'peak_value': 3000.0 # Not used by stop loss
    }
    sl_alerts = check_stop_loss_per_position(mock_holdings_details_loss, risk_parameters['stop_loss_pct'], verbose=True)
    for alert in sl_alerts:
        print(f"{LogColors.FAIL}  ALERT: {alert}{LogColors.ENDC}") # Using FAIL for test alerts
    assert any(a.alert_type == 'STOP_LOSS_PER_POSITION' and a.symbol == 'AAPL' for a in sl_alerts)

    # Test Max Position Size (Post-trade)
    print("\nTesting Max Position Size (Post-trade):")
    portfolio_state_ps = {
        'holdings_details': mock_holdings_details_pos_size,
        'total_value': 30000.0, 
        'peak_value': 35000.0
    }
    ps_alerts = check_max_position_size(mock_holdings_details_pos_size, portfolio_state_ps['total_value'], risk_parameters['max_pos_pct'], verbose=True)
    for alert in ps_alerts:
        print(f"{LogColors.FAIL}  ALERT: {alert}{LogColors.ENDC}")
    assert any(a.alert_type == 'MAX_POSITION_SIZE' and a.symbol == 'GOOG' for a in ps_alerts)

    # Test Max Position Size (Pre-trade)
    print("\nTesting Max Position Size (Pre-trade):")
    # Assume current portfolio has 10k value, and we want to buy GOOG which would make its value 5k (50%)
    existing_holdings_for_pre_trade = [
        {'symbol': 'CashCow', 'average_cost_price': 100.0, 'current_price': 100.0, 'quantity': 50, 'market_value': 5000.0}
    ]
    pre_trade_total_value = 10000.0 # Assume 5k cash + 5k CashCow
    pre_ps_alerts = check_max_position_size(
        existing_holdings_for_pre_trade, 
        pre_trade_total_value, 
        risk_parameters['max_pos_pct'], 
        symbol_being_traded='GOOG', 
        potential_new_market_value=5000.0, # This trade would make GOOG 50% of portfolio
        verbose=True
    )
    for alert in pre_ps_alerts:
        print(f"{LogColors.FAIL}  ALERT: {alert}{LogColors.ENDC}")
    assert any(a.alert_type == 'MAX_POSITION_SIZE_PRE_TRADE' and a.symbol == 'GOOG' for a in pre_ps_alerts)


    # Test Max Account Drawdown
    print("\nTesting Max Account Drawdown:")
    portfolio_state_dd = {
        'holdings_details': [], # Holdings content doesn't matter for this specific check
        'total_value': 8000.0, 
        'peak_value': 10000.0 # 20% drawdown
    }
    dd_alerts = check_max_account_drawdown(portfolio_state_dd['total_value'], portfolio_state_dd['peak_value'], risk_parameters['max_dd_pct'], verbose=True)
    for alert in dd_alerts:
        print(f"{LogColors.FAIL}  ALERT: {alert}{LogColors.ENDC}")
    assert any(a.alert_type == 'MAX_ACCOUNT_DRAWDOWN' for a in dd_alerts)

    # Test Evaluate All Risks
    print("\nTesting Evaluate All Risks (combining scenarios):")
    # AAPL has 13.33% loss (150 -> 130), GOOG is 70% of portfolio, Drawdown is (10000-8450)/10000 = 15.5%
    combined_holdings = [
        {'symbol': 'AAPL', 'average_cost_price': 150.0, 'current_price': 130.0, 'quantity': 10, 'market_value': 1300.0}, # Loss > 10%
        {'symbol': 'GOOG', 'average_cost_price': 2000.0, 'current_price': 2100.0, 'quantity': 3, 'market_value': 6300.0}, # 6300 / (8450) = ~74% > 25%
         {'symbol': 'SAFE', 'average_cost_price': 100.0, 'current_price': 100.0, 'quantity': 8.5, 'market_value': 850.0}
    ]
    # total market value = 1300 + 6300 + 850 = 8450. Assume no cash for this test. 
    # So total_value = 8450
    portfolio_state_all = {
        'holdings_details': combined_holdings,
        'total_value': 8450.0, 
        'peak_value': 10000.0 # Drawdown = (10000 - 8450)/10000 = 0.155 (15.5%) > 15%
    }
    all_risk_alerts = evaluate_all_risks(portfolio_state_all, risk_parameters, verbose=True)
    print("\nAll Alerts from evaluate_all_risks:")
    for alert in all_risk_alerts:
        print(f"{LogColors.FAIL}  ALERT: {alert}{LogColors.ENDC}")
    
    assert any(a.alert_type == 'STOP_LOSS_PER_POSITION' and a.symbol == 'AAPL' for a in all_risk_alerts)
    assert any(a.alert_type == 'MAX_POSITION_SIZE' and a.symbol == 'GOOG' for a in all_risk_alerts)
    assert any(a.alert_type == 'MAX_ACCOUNT_DRAWDOWN' for a in all_risk_alerts)
    print(f"Number of alerts: {len(all_risk_alerts)}")
    assert len(all_risk_alerts) >= 3 # Could be more if GOOG triggers both general and pre-trade in some setup

    print("\n--- RiskManager Test Finished ---") 
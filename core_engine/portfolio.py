import time # Added import for time module
from typing import Dict, Any, Optional, Callable

class MockPortfolio:
    """
    Manages a mock portfolio with cash and holdings.
    Tracks average cost price for holdings.
    """
    def __init__(self, initial_cash: float):
        if initial_cash < 0:
            raise ValueError("Initial cash cannot be negative.")
        self.cash: float = initial_cash
        # holdings structure: {'SYMBOL': {'quantity': int, 'average_cost_price': float}}
        self.holdings: Dict[str, Dict[str, Any]] = {}
        # Adding a verbose flag, though not strictly used by original prints yet
        self.verbose: bool = True # Default to True for now to ensure logs are visible
        if self.verbose:
            print(f"MockPortfolio: Initialized with cash: {self.cash:.2f}")

    def get_cash(self) -> float:
        """Returns the current cash balance."""
        return self.cash

    def get_holdings(self) -> Dict[str, Dict[str, Any]]:
        """Returns the current holdings."""
        return self.holdings.copy() # Return a copy to prevent external modification

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Returns the position details for a given symbol, or None if not held."""
        return self.holdings.get(symbol)

    def get_holdings_value(self, current_price_callback: Optional[Callable[[str], Optional[float]]] = None) -> float:
        """
        Calculates the total market value of all holdings.

        Args:
            current_price_callback: An optional function that takes a symbol (str) 
                                      and returns its current price (float), or None if not available.
        
        Returns:
            The total market value of all current holdings.
        """
        total_holdings_val = 0.0
        if not current_price_callback:
            # If no callback is provided, we cannot determine market value accurately.
            # Depending on requirements, could return sum of average cost prices, but market value is usually preferred.
            # For now, returning 0 as we need live prices for true market value.
            print("Warning: get_holdings_value called without current_price_callback. Market value will be 0.")
            return 0.0

        for symbol, details in self.holdings.items():
            current_price = current_price_callback(symbol)
            if current_price is not None and current_price > 0:
                total_holdings_val += details['quantity'] * current_price
            else:
                # If price for a holding isn't available or is invalid, its market value is considered 0.
                print(f"Warning: Current price for symbol {symbol} not available or invalid in get_holdings_value. Market value for this holding considered 0.")
        return total_holdings_val

    def record_transaction(self, 
                           symbol: str, 
                           transaction_type: str, # 'BUY' or 'SELL'
                           quantity: int, 
                           price: float,
                           timestamp: float # For logging or future use
                           ) -> bool:
        """
        Records a transaction, updates holdings and cash.

        Args:
            symbol: The stock symbol.
            transaction_type: 'BUY' or 'SELL'.
            quantity: The number of shares.
            price: The price per share.
            timestamp: The time of the transaction.

        Returns:
            True if the transaction was successful, False otherwise.
        """
        # Use ctime for human-readable logs
        log_timestamp = time.ctime(timestamp)

        if quantity <= 0:
            if self.verbose:
                print(f"MockPortfolio: Transaction Error for {symbol} at {log_timestamp}. Quantity must be positive, got {quantity}.")
            return False
        if price <= 0:
            if self.verbose:
                print(f"MockPortfolio: Transaction Error for {symbol} at {log_timestamp}. Price must be positive, got {price}.")
            return False

        cost_or_proceeds = quantity * price
        transaction_type_upper = transaction_type.upper()

        if transaction_type_upper == 'BUY':
            if self.cash < cost_or_proceeds:
                if self.verbose:
                    print(f"MockPortfolio: Transaction Error for BUY {quantity} {symbol} at {price:.2f} (Timestamp: {log_timestamp}). Insufficient cash. "
                          f"Required: {cost_or_proceeds:.2f}, Available: {self.cash:.2f}")
                return False
            
            self.cash -= cost_or_proceeds
            current_position = self.holdings.get(symbol)
            if current_position:
                current_quantity = current_position['quantity']
                current_avg_cost = current_position['average_cost_price']
                
                new_total_cost = (current_avg_cost * current_quantity) + cost_or_proceeds
                new_total_quantity = current_quantity + quantity
                new_average_cost = new_total_cost / new_total_quantity
                
                current_position['quantity'] = new_total_quantity
                current_position['average_cost_price'] = new_average_cost
            else:
                self.holdings[symbol] = {'quantity': quantity, 'average_cost_price': price}
            
            if self.verbose:
                print(f"MockPortfolio: Transaction Recorded - BUY {quantity} {symbol} @ {price:.2f}. Cost: {cost_or_proceeds:.2f}. Timestamp: {log_timestamp}. New Cash: {self.cash:.2f}. New Holdings for {symbol}: {self.holdings[symbol]}")
            return True

        elif transaction_type_upper == 'SELL':
            current_position = self.holdings.get(symbol)
            if not current_position or current_position['quantity'] < quantity:
                current_qty_held = current_position['quantity'] if current_position else 0
                if self.verbose:
                    print(f"MockPortfolio: Transaction Error for SELL {quantity} {symbol} at {price:.2f} (Timestamp: {log_timestamp}). Insufficient shares. "
                          f"Attempting to sell {quantity}, Held: {current_qty_held}")
                return False

            self.cash += cost_or_proceeds
            original_quantity = current_position['quantity']
            current_position['quantity'] -= quantity
            
            if self.verbose:
                if current_position['quantity'] == 0:
                    del self.holdings[symbol]
                    print(f"MockPortfolio: Transaction Recorded - SELL {quantity} {symbol} @ {price:.2f}. Proceeds: {cost_or_proceeds:.2f}. Timestamp: {log_timestamp}. All {original_quantity} shares sold. New Cash: {self.cash:.2f}. {symbol} removed from holdings.")
                else:
                    print(f"MockPortfolio: Transaction Recorded - SELL {quantity} {symbol} @ {price:.2f}. Proceeds: {cost_or_proceeds:.2f}. Timestamp: {log_timestamp}. Remaining {symbol}: {current_position['quantity']}. New Cash: {self.cash:.2f}")
            return True
        else:
            if self.verbose:
                print(f"MockPortfolio: Transaction Error for {symbol} at {log_timestamp}. Invalid transaction type '{transaction_type}'. Must be 'BUY' or 'SELL'.")
            return False

    def get_position_value(self, symbol: str, current_price: float) -> float:
        """Calculates the current market value of a specific position."""
        position = self.get_position(symbol)
        if position and current_price > 0:
            return position['quantity'] * current_price
        return 0.0

    def get_total_portfolio_value(self, current_price_callback: Optional[Callable[[str], Optional[float]]] = None) -> float:
        """
        Calculates the total current value of the portfolio (cash + market value of all holdings).
        
        Args:
            current_price_callback: An optional function that takes a symbol (str) 
                                      and returns its current price (float), or None if not available.
        
        Returns:
            The total portfolio value.
        """
        return self.cash + self.get_holdings_value(current_price_callback)

if __name__ == '__main__':
    # Example Usage for MockPortfolio
    print("\n--- MockPortfolio Test ---")
    portfolio = MockPortfolio(initial_cash=10000.00)
    print(f"Initial Cash: {portfolio.get_cash():.2f}")
    print(f"Initial Holdings: {portfolio.get_holdings()}")

    # Buy AAPL
    portfolio.record_transaction('AAPL', 'BUY', 10, 150.00, time.time())
    # Buy MSFT
    portfolio.record_transaction('MSFT', 'BUY', 5, 280.00, time.time())
    
    # Buy more AAPL at a different price
    portfolio.record_transaction('AAPL', 'BUY', 5, 155.00, time.time())

    print(f"Holdings after buys: {portfolio.get_holdings()}")
    print(f"Cash after buys: {portfolio.get_cash():.2f}")

    # Sell some AAPL
    portfolio.record_transaction('AAPL', 'SELL', 8, 160.00, time.time())
    
    # Attempt to sell more AAPL than held
    portfolio.record_transaction('AAPL', 'SELL', 10, 161.00, time.time()) # Should fail

    # Attempt to buy with insufficient funds
    portfolio.record_transaction('GOOG', 'BUY', 100, 2500.00, time.time()) # Should fail

    print(f"Holdings after sell attempt: {portfolio.get_holdings()}")
    print(f"Cash after sell attempt: {portfolio.get_cash():.2f}")

    # Sell all remaining MSFT
    portfolio.record_transaction('MSFT', 'SELL', 5, 290.00, time.time())
    print(f"Holdings after selling all MSFT: {portfolio.get_holdings()}")
    print(f"Cash: {portfolio.get_cash():.2f}")

    # Calculate total portfolio value
    # current_market_prices = {'AAPL': 158.00, 'MSFT': 292.00, 'GOOG': 2400.00} 
    # Note: MSFT price is for a stock no longer held, GOOG price is for a stock never successfully bought.
    #       This is fine, get_total_portfolio_value will only use prices for current holdings.
    
    # Updated test to use a callback style function for prices
    def get_mock_current_prices(symbol: str) -> Optional[float]:
        prices = {'AAPL': 158.00, 'MSFT': 292.00, 'GOOG': 2400.00}
        return prices.get(symbol)

    total_value = portfolio.get_total_portfolio_value(current_price_callback=get_mock_current_prices)
    print(f"Current market prices via callback for AAPL: {get_mock_current_prices('AAPL')}")
    print(f"Total portfolio value: {total_value:.2f}")

    holdings_val = portfolio.get_holdings_value(current_price_callback=get_mock_current_prices)
    print(f"Total holdings value: {holdings_val:.2f}")

    pos_val_aapl = portfolio.get_position_value('AAPL', get_mock_current_prices('AAPL') or 0)
    print(f"Current AAPL position value: {pos_val_aapl:.2f}")
    
    pos_val_msft = portfolio.get_position_value('MSFT', get_mock_current_prices('MSFT') or 0) # Should be 0 as MSFT is sold
    print(f"Current MSFT position value: {pos_val_msft:.2f}")

    print("--- MockPortfolio Test Finished ---") 
import time # Added import for time module
from typing import Dict, Any, Optional, Callable, List, Tuple

class MockPortfolio:
    """
    Manages a mock portfolio with cash and holdings.
    Tracks average cost price for holdings and P&L.
    """
    def __init__(self, initial_cash: float, verbose: bool = False):
        if initial_cash < 0:
            raise ValueError("Initial cash cannot be negative.")
        self.cash: float = initial_cash
        self.peak_portfolio_value: float = initial_cash # Initialize peak value
        # holdings structure: {'SYMBOL': {'quantity': int, 'average_cost_price': float}}
        self.holdings: Dict[str, Dict[str, Any]] = {}
        self.realized_pnl: float = 0.0
        self.verbose: bool = verbose # Use the passed verbose parameter
        if self.verbose:
            print(f"MockPortfolio: Initialized with cash: {self.cash:.2f}, Realized P&L: {self.realized_pnl:.2f}, Peak Portfolio Value: {self.peak_portfolio_value:.2f}")

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

            avg_cost_price = current_position['average_cost_price']
            transaction_realized_pnl = (price - avg_cost_price) * quantity
            self.realized_pnl += transaction_realized_pnl
            
            self.cash += cost_or_proceeds
            original_quantity = current_position['quantity']
            current_position['quantity'] -= quantity
            
            if self.verbose:
                pnl_message = f"Transaction P&L: {transaction_realized_pnl:.2f}. Cumulative Realized P&L: {self.realized_pnl:.2f}."
                if current_position['quantity'] == 0:
                    del self.holdings[symbol]
                    print(f"MockPortfolio: Transaction Recorded - SELL {quantity} {symbol} @ {price:.2f}. Proceeds: {cost_or_proceeds:.2f}. Timestamp: {log_timestamp}. All {original_quantity} shares sold. {pnl_message} New Cash: {self.cash:.2f}. {symbol} removed from holdings.")
                else:
                    print(f"MockPortfolio: Transaction Recorded - SELL {quantity} {symbol} @ {price:.2f}. Proceeds: {cost_or_proceeds:.2f}. Timestamp: {log_timestamp}. Remaining {symbol}: {current_position['quantity']}. {pnl_message} New Cash: {self.cash:.2f}")
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
        current_holdings_value = self.get_holdings_value(current_price_callback)
        total_value = self.cash + current_holdings_value
        
        # Update peak portfolio value
        if total_value > self.peak_portfolio_value:
            if self.verbose and self.peak_portfolio_value != total_value: # Log only if it changes
                print(f"MockPortfolio: Peak portfolio value updated from {self.peak_portfolio_value:.2f} to {total_value:.2f}")
            self.peak_portfolio_value = total_value
            
        return total_value

    def get_peak_portfolio_value(self) -> float:
        """Returns the peak portfolio value recorded so far."""
        return self.peak_portfolio_value

    def get_realized_pnl(self) -> float:
        """Returns the cumulative realized P&L."""
        return self.realized_pnl

    def get_unrealized_pnl(self, current_price_callback: Optional[Callable[[str], Optional[float]]] = None) -> float:
        """Calculates the total unrealized P&L for all current holdings."""
        if not current_price_callback:
            if self.verbose:
                print("MockPortfolio: Warning - get_unrealized_pnl called without current_price_callback. Unrealized P&L will be 0.")
            return 0.0
        
        total_unrealized_pnl = 0.0
        for symbol, details in self.holdings.items():
            current_price = current_price_callback(symbol)
            if current_price is not None and current_price > 0:
                unrealized_pnl_for_holding = (current_price - details['average_cost_price']) * details['quantity']
                total_unrealized_pnl += unrealized_pnl_for_holding
            else:
                if self.verbose:
                    print(f"MockPortfolio: Warning - Current price for symbol {symbol} not available or invalid in get_unrealized_pnl. Unrealized P&L for this holding considered 0.")
        return total_unrealized_pnl

    def get_total_pnl(self, current_price_callback: Optional[Callable[[str], Optional[float]]] = None) -> float:
        """Calculates the total P&L (realized + unrealized)."""
        return self.get_realized_pnl() + self.get_unrealized_pnl(current_price_callback)

    def get_holdings_with_details(self, current_price_callback: Optional[Callable[[str], Optional[float]]] = None) -> List[Dict[str, Any]]:
        """
        Returns a list of dictionaries, each containing detailed information for a holding,
        including quantity, average_cost_price, current_price, market_value, and unrealized_pnl.
        """
        holdings_details_list = []
        if not current_price_callback:
            if self.verbose:
                print("MockPortfolio: Warning - get_holdings_with_details called without current_price_callback. Price-dependent details will be missing or zero.")
            # Still return basic info if price callback is missing
            for symbol, details in self.holdings.items():
                holdings_details_list.append({
                    'symbol': symbol,
                    'quantity': details['quantity'],
                    'average_cost_price': details['average_cost_price'],
                    'current_price': None,
                    'market_value': 0.0,
                    'unrealized_pnl': 0.0
                })
            return holdings_details_list

        for symbol, details in self.holdings.items():
            current_price = current_price_callback(symbol)
            market_value = 0.0
            unrealized_pnl = 0.0
            valid_price = current_price is not None and current_price > 0

            if valid_price:
                market_value = details['quantity'] * current_price
                unrealized_pnl = (current_price - details['average_cost_price']) * details['quantity']
            
            holdings_details_list.append({
                'symbol': symbol,
                'quantity': details['quantity'],
                'average_cost_price': details['average_cost_price'],
                'current_price': current_price if valid_price else None,
                'market_value': market_value,
                'unrealized_pnl': unrealized_pnl
            })
        return holdings_details_list

    def get_asset_allocation_percentages(self, current_price_callback: Optional[Callable[[str], Optional[float]]] = None) -> Dict[str, float]:
        """
        Calculates the percentage of each asset's market value relative to the total portfolio net worth.
        Returns a dictionary like {'MSFT': 0.4, 'AAPL': 0.6}.
        Assets with no or invalid current price will be excluded.
        """
        allocation = {}
        if not current_price_callback:
            if self.verbose:
                print("MockPortfolio: Warning - get_asset_allocation_percentages called without current_price_callback. Allocation will be empty.")
            return allocation

        total_portfolio_net_worth = self.get_total_portfolio_value(current_price_callback)
        if total_portfolio_net_worth == 0: # Avoid division by zero if portfolio value is zero (e.g. no cash, no valid prices)
            if self.verbose and self.holdings: # only print if there are holdings but value is zero
                 print("MockPortfolio: Warning - Total portfolio net worth is 0. Asset allocation will be empty.")
            return allocation

        for symbol, details in self.holdings.items():
            current_price = current_price_callback(symbol)
            if current_price is not None and current_price > 0:
                market_value = details['quantity'] * current_price
                percentage = (market_value / total_portfolio_net_worth) * 100.0 if total_portfolio_net_worth else 0
                allocation[symbol] = round(percentage, 2) # Store as percentage, rounded
            else:
                if self.verbose:
                    print(f"MockPortfolio: Warning - Current price for {symbol} not available for asset allocation. It will be excluded.")
        return allocation

if __name__ == '__main__':
    # Example Usage for MockPortfolio
    print("\n--- MockPortfolio Test ---")
    portfolio = MockPortfolio(initial_cash=100000.00) # Increased initial cash for more robust testing
    print(f"Initial Cash: {portfolio.get_cash():.2f}, Realized P&L: {portfolio.get_realized_pnl():.2f}")
    print(f"Initial Holdings: {portfolio.get_holdings()}")

    # Mock current price provider for testing
    mock_prices = {'AAPL': 150.0, 'MSFT': 280.0, 'GOOG': 2200.0}
    def get_mock_current_prices(symbol: str) -> Optional[float]:
        return mock_prices.get(symbol)

    # Buy AAPL
    portfolio.record_transaction('AAPL', 'BUY', 10, mock_prices['AAPL'], time.time())
    # Buy MSFT
    mock_prices['MSFT'] = 280.0 # Set price before buy
    portfolio.record_transaction('MSFT', 'BUY', 5, mock_prices['MSFT'], time.time())
    
    # Buy more AAPL at a different price
    mock_prices['AAPL'] = 155.0 # Simulate price change
    portfolio.record_transaction('AAPL', 'BUY', 5, mock_prices['AAPL'], time.time())

    print(f"\nHoldings after buys: {portfolio.get_holdings()}")
    print(f"Cash after buys: {portfolio.get_cash():.2f}")
    print(f"Realized P&L after buys: {portfolio.get_realized_pnl():.2f}")
    print(f"Unrealized P&L after buys: {portfolio.get_unrealized_pnl(get_mock_current_prices):.2f}")
    print(f"Total P&L after buys: {portfolio.get_total_pnl(get_mock_current_prices):.2f}")
    print(f"Total Portfolio Value after buys: {portfolio.get_total_portfolio_value(get_mock_current_prices):.2f}")

    # Sell some AAPL
    mock_prices['AAPL'] = 160.0 # Simulate price change for selling
    portfolio.record_transaction('AAPL', 'SELL', 8, mock_prices['AAPL'], time.time())
    print(f"\nAfter selling 8 AAPL @ {mock_prices['AAPL']:.2f}:")
    print(f"Holdings: {portfolio.get_holdings()}")
    print(f"Cash: {portfolio.get_cash():.2f}")
    print(f"Realized P&L: {portfolio.get_realized_pnl():.2f}")
    print(f"Unrealized P&L: {portfolio.get_unrealized_pnl(get_mock_current_prices):.2f}") # AAPL price is 160
    print(f"Total P&L: {portfolio.get_total_pnl(get_mock_current_prices):.2f}")
    print(f"Total Portfolio Value: {portfolio.get_total_portfolio_value(get_mock_current_prices):.2f}")

    # Update MSFT price and check P&L
    mock_prices['MSFT'] = 290.0
    print(f"\nMSFT price updated to {mock_prices['MSFT']:.2f}:")
    print(f"Unrealized P&L for MSFT: {(mock_prices['MSFT'] - portfolio.get_position('MSFT')['average_cost_price']) * portfolio.get_position('MSFT')['quantity'] if portfolio.get_position('MSFT') else 0:.2f}")
    print(f"Total Unrealized P&L: {portfolio.get_unrealized_pnl(get_mock_current_prices):.2f}")
    print(f"Total P&L: {portfolio.get_total_pnl(get_mock_current_prices):.2f}")
    print(f"Total Portfolio Value: {portfolio.get_total_portfolio_value(get_mock_current_prices):.2f}")

    # Sell all remaining MSFT
    mock_prices['MSFT'] = 295.0 # Price for selling MSFT
    msft_position = portfolio.get_position('MSFT')
    if msft_position:
        portfolio.record_transaction('MSFT', 'SELL', msft_position['quantity'], mock_prices['MSFT'], time.time())
    print(f"\nAfter selling all MSFT @ {mock_prices['MSFT']:.2f}:")
    print(f"Holdings: {portfolio.get_holdings()}")
    print(f"Cash: {portfolio.get_cash():.2f}")
    print(f"Realized P&L: {portfolio.get_realized_pnl():.2f}")
    print(f"Unrealized P&L: {portfolio.get_unrealized_pnl(get_mock_current_prices):.2f}")
    print(f"Total P&L: {portfolio.get_total_pnl(get_mock_current_prices):.2f}")
    print(f"Total Portfolio Value: {portfolio.get_total_portfolio_value(get_mock_current_prices):.2f}")

    # Test detailed holdings
    print("\nDetailed Holdings:")
    detailed_holdings = portfolio.get_holdings_with_details(get_mock_current_prices)
    for item in detailed_holdings:
        print(item)
    
    # Test Asset Allocation
    # Buy GOOG to test allocation with multiple assets
    mock_prices['GOOG'] = 2250.0
    portfolio.record_transaction('GOOG', 'BUY', 2, mock_prices['GOOG'], time.time()) # Cash: 100000 - 1500 - 1400 - 775 + 1280 + 1475 - 4500 = 94580
    # AAPL remaining: 10+5-8 = 7. Avg cost: ((10*150)+(5*155))/(10+5) = (1500+775)/15 = 2275/15 = 151.666
    # Current AAPL price 160. MSFT sold. GOOG price 2250.
    # Portfolio: Cash 94580. 
    # AAPL: 7 * 160 = 1120. 
    # GOOG: 2 * 2250 = 4500
    # Total Value: 94580 + 1120 + 4500 = 100200
    print("\nPortfolio after buying GOOG:")
    print(f"Cash: {portfolio.get_cash():.2f}")
    print(f"Holdings: {portfolio.get_holdings()}")
    print(f"Total Portfolio Value: {portfolio.get_total_portfolio_value(get_mock_current_prices):.2f}")
    
    print("\nAsset Allocation:")
    asset_allocation = portfolio.get_asset_allocation_percentages(get_mock_current_prices)
    print(asset_allocation)

    # Test edge case: no price callback for allocation
    print("\nAsset Allocation (no price callback):")
    print(portfolio.get_asset_allocation_percentages(None))

    # Test edge case: sell all, then check allocation (should be empty or show 0 for everything)
    goog_position = portfolio.get_position('GOOG')
    if goog_position:
        portfolio.record_transaction('GOOG', 'SELL', goog_position['quantity'], 2300, time.time())
    aapl_position = portfolio.get_position('AAPL')
    if aapl_position:
        portfolio.record_transaction('AAPL', 'SELL', aapl_position['quantity'], 165, time.time())
    print("\nPortfolio after selling all remaining assets:")
    print(f"Holdings: {portfolio.get_holdings()}")
    print(f"Total Portfolio Value: {portfolio.get_total_portfolio_value(get_mock_current_prices):.2f}") # Should be just cash
    print(f"Cash: {portfolio.get_cash():.2f}")
    print(f"Realized P&L: {portfolio.get_realized_pnl():.2f}")
    print(f"Unrealized P&L: {portfolio.get_unrealized_pnl(get_mock_current_prices):.2f}") # Should be 0
    print("\nAsset Allocation (no holdings):")
    print(portfolio.get_asset_allocation_percentages(get_mock_current_prices))

    print("\n--- End MockPortfolio Test ---") 
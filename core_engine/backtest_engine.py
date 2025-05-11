import pandas as pd

def run_backtest(
    data_with_signals: pd.DataFrame,
    initial_capital: float,
    commission_rate_pct: float = 0.0, # 手续费率 (例如 0.0005 代表 0.05%)
    min_commission: float = 0.0,      # 最低手续费 (例如 5.0)
    slippage_pct: float = 0.0, # 新增：滑点百分比 (例如 0.0001 代表 0.01%)
    close_col: str = 'close',
    signal_col: str = 'signal',
    symbol_col: str = 'symbol'
):
    """
    执行简单的事件驱动回测，支持多股票代码，并考虑交易手续费和滑点。

    参数:
    data_with_signals (pd.DataFrame): 包含价格数据和交易信号的DataFrame。
                                      索引必须是日期时间。
                                      列应包括 close_col, signal_col, symbol_col。
    initial_capital (float): 初始资金。
    commission_rate_pct (float): 交易手续费率（百分比的小数表示，例如0.05%应传入0.0005）。
    min_commission (float): 每笔交易的最低手续费。
    slippage_pct (float): 应用于每笔交易的滑点百分比。
                          买入时价格增加，卖出时价格减少。
    close_col (str): 收盘价列名。
    signal_col (str): 交易信号列名 (1 for Buy, -1 for Sell, 0 for Hold)。
    symbol_col (str): 股票代码列名。

    返回:
    tuple: (portfolio_history_df, trades_df)
        portfolio_history_df (pd.DataFrame): 每日投资组合价值历史。
                                            列: ['timestamp', 'cash', 'holdings_value', 'total_value', 'returns']
        trades_df (pd.DataFrame): 交易记录列表。
                                  列: ['timestamp', 'symbol', 'action', 'quantity', 'price', 'cost', 'commission']
    """
    cash = initial_capital
    holdings = {}  # key: symbol, value: quantity (float for shares)
    portfolio_value_over_time = []
    trades_log = []
    last_prices = {} # Stores last known price for each symbol {symbol: price}

    # 确保data_with_signals的索引是唯一的日期
    if not isinstance(data_with_signals.index, pd.DatetimeIndex):
        raise ValueError("DataFrame的索引必须是pd.DatetimeIndex类型")

    unique_dates = data_with_signals.index.unique().sort_values()

    for current_date in unique_dates:
        # 获取当天的所有股票数据
        current_day_data_for_date = data_with_signals.loc[data_with_signals.index == current_date]
        
        # 更新当日股票价格到last_prices
        for _, row in current_day_data_for_date.iterrows():
            last_prices[row[symbol_col]] = row[close_col]
        
        # 处理交易信号并执行交易
        for _, row in current_day_data_for_date.iterrows():
            symbol = row[symbol_col]
            signal = row[signal_col]
            price_at_signal = row[close_col] # 信号发出时的价格，作为滑点计算的基础

            fixed_trade_quantity = 10 # 简化：固定交易10股
            commission_this_trade = 0.0
            actual_execution_price = price_at_signal # 初始化实际执行价格

            if signal == 1:  # 买入信号
                # 仅当未持有或持仓为0时买入 (简化)
                if holdings.get(symbol, 0) == 0:
                    actual_execution_price = price_at_signal * (1 + slippage_pct) # 应用买入滑点
                    cost_of_trade_before_commission = fixed_trade_quantity * actual_execution_price
                    
                    # 计算手续费
                    commission_this_trade = cost_of_trade_before_commission * commission_rate_pct
                    if commission_this_trade < min_commission:
                        commission_this_trade = min_commission
                    
                    total_cost_of_trade = cost_of_trade_before_commission + commission_this_trade

                    if cash >= total_cost_of_trade:
                        holdings[symbol] = holdings.get(symbol, 0) + fixed_trade_quantity
                        cash -= total_cost_of_trade # 扣除包含手续费的总成本
                        trades_log.append({
                            'timestamp': current_date, 'symbol': symbol, 'action': 'BUY',
                            'quantity': fixed_trade_quantity, 'price': actual_execution_price, # 记录含滑点的价格 
                            'cost': cost_of_trade_before_commission, # 记录未含手续费的成本
                            'commission': commission_this_trade
                        })
            elif signal == -1:  # 卖出信号
                if holdings.get(symbol, 0) > 0:
                    quantity_held = holdings[symbol]
                    actual_execution_price = price_at_signal * (1 - slippage_pct) # 应用卖出滑点
                    proceeds_before_commission = quantity_held * actual_execution_price
                    
                    # 计算手续费
                    commission_this_trade = proceeds_before_commission * commission_rate_pct
                    if commission_this_trade < min_commission:
                        commission_this_trade = min_commission

                    net_proceeds = proceeds_before_commission - commission_this_trade

                    cash += net_proceeds # 增加扣除手续费后的净收益
                    holdings[symbol] = 0  # 简化：卖出该股票全部持仓
                    trades_log.append({
                        'timestamp': current_date, 'symbol': symbol, 'action': 'SELL',
                        'quantity': quantity_held, 'price': actual_execution_price, # 记录含滑点的价格
                        'cost': -proceeds_before_commission, # 记录未含手续费的成本 (负数代表收入)
                        'commission': commission_this_trade
                    })
        
        # 计算当日交易结束后的持仓总价值
        current_holdings_value = 0
        for symbol_in_portfolio, quantity_in_portfolio in holdings.items():
            if quantity_in_portfolio > 0:
                asset_price_for_valuation = last_prices.get(symbol_in_portfolio, 0) # 使用最新价格估值
                if asset_price_for_valuation <= 0: # 如果价格无效或未获取到
                    # 尝试从原始数据中获取该股票在当日或之前的最后有效价格（更复杂，暂不实现）
                    # print(f"警告: 股票 {symbol_in_portfolio} 在 {current_date} 的价格无效或未找到，估值可能不准。")
                    pass # 简单处理：如果价格是0或负，这部分价值为0
                current_holdings_value += quantity_in_portfolio * asset_price_for_valuation
        
        total_portfolio_value = cash + current_holdings_value
        portfolio_value_over_time.append({
            'timestamp': current_date,
            'cash': cash,
            'holdings_value': current_holdings_value,
            'total_value': total_portfolio_value
        })

    portfolio_history_df = pd.DataFrame(portfolio_value_over_time)
    if not portfolio_history_df.empty:
        portfolio_history_df.set_index('timestamp', inplace=True) # 将timestamp设为索引
        portfolio_history_df['returns'] = portfolio_history_df['total_value'].pct_change().fillna(0)

    trades_df = pd.DataFrame(trades_log)
    if not trades_df.empty and 'timestamp' in trades_df.columns:
        trades_df.set_index('timestamp', inplace=True) # 可选，将timestamp设为索引

    return portfolio_history_df, trades_df

if __name__ == '__main__':
    # 构造一个简单的测试用例
    test_data_list = []
    dates = pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05'])
    for date_val in dates:
        test_data_list.append({'Date': date_val, 'symbol': 'STOCK_A', 'close': 10, 'signal': 0})
        test_data_list.append({'Date': date_val, 'symbol': 'STOCK_B', 'close': 20, 'signal': 0})
    
    data_signals = pd.DataFrame(test_data_list)
    data_signals.set_index('Date', inplace=True)

    # 模拟一些信号
    data_signals.loc[(data_signals.index == '2023-01-02') & (data_signals['symbol'] == 'STOCK_A'), 'signal'] = 1  # 买入 A
    data_signals.loc[(data_signals.index == '2023-01-02') & (data_signals['symbol'] == 'STOCK_A'), 'close'] = 11
    
    data_signals.loc[(data_signals.index == '2023-01-03') & (data_signals['symbol'] == 'STOCK_B'), 'signal'] = 1  # 买入 B
    data_signals.loc[(data_signals.index == '2023-01-03') & (data_signals['symbol'] == 'STOCK_B'), 'close'] = 22 

    data_signals.loc[(data_signals.index == '2023-01-04') & (data_signals['symbol'] == 'STOCK_A'), 'signal'] = -1 # 卖出 A
    data_signals.loc[(data_signals.index == '2023-01-04') & (data_signals['symbol'] == 'STOCK_A'), 'close'] = 12
    
    data_signals.loc[(data_signals.index == '2023-01-05') & (data_signals['symbol'] == 'STOCK_B'), 'close'] = 25 # B 价格上涨

    print("--- 测试用信号数据 ---")
    print(data_signals)

    initial_capital = 10000.0
    # 测试手续费
    test_commission_rate = 0.0005 # 0.05%
    test_min_commission = 5.0    # 最低5元

    print(f"\\n--- 测试手续费: 费率={test_commission_rate*100}%, 最低={test_min_commission} ---")
    portfolio_history, trades = run_backtest(data_signals, initial_capital, 
                                             commission_rate_pct=test_commission_rate, 
                                             min_commission=test_min_commission)

    print("\n--- 投资组合历史 (含手续费) ---")
    print(portfolio_history)
    print("\n--- 交易记录 ---")
    print(trades) 
import time
from core_engine.realtime_feed import MockRealtimeDataProvider # DataTick not directly used here anymore
from strategies.simple_ma_strategy import RealtimeSimpleMAStrategy
from core_engine.portfolio import MockPortfolio # Import MockPortfolio
from core_engine.trading_engine import MockTradingEngine # Import MockTradingEngine

def main():
    print("启动完整的实时模拟交易流程...")
    initial_cash = 100000.00 # 初始资金
    fixed_trade_qty = 100     # 固定交易数量
    run_duration_seconds = 30 # 模拟运行时长

    # 1. 配置和实例化 MockRealtimeDataProvider
    mock_provider_config = [
        {'symbol': 'SIM_STOCK_A', 'initial_price': 100.0, 'volatility': 0.01, 'interval_seconds': 1.0},
        {'symbol': 'SIM_STOCK_B', 'initial_price': 50.0, 'volatility': 0.02, 'interval_seconds': 1.5} 
    ]
    data_provider = MockRealtimeDataProvider(symbols_config=mock_provider_config, verbose=False) # Provider verbose off to reduce noise

    # 2. 实例化 MockPortfolio
    portfolio = MockPortfolio(initial_cash=initial_cash)
    print(f"初始资金: {portfolio.get_cash():.2f}")

    # 3. 实例化 MockTradingEngine
    trading_engine = MockTradingEngine(
        portfolio=portfolio, 
        fixed_trade_quantity=fixed_trade_qty, 
        verbose=True # Engine verbose on to see trade attempts
    )

    # 4. 配置和实例化 RealtimeSimpleMAStrategy (例如，一个用于 SIM_STOCK_A)
    strategy_symbol_A = 'SIM_STOCK_A'
    short_window_A = 5
    long_window_A = 12
    
    print(f"为股票 {strategy_symbol_A} 初始化实时MA策略 (SW:{short_window_A}, LW:{long_window_A}).")
    strategy_A = RealtimeSimpleMAStrategy(
        symbol=strategy_symbol_A,
        short_window=short_window_A,
        long_window=long_window_A,
        data_provider=data_provider,
        verbose=True, # Strategy verbose on to see its signal decisions
        signal_callback=trading_engine.handle_signal_event # 连接到交易引擎
    )

    # (可选) 可以为 SIM_STOCK_B 设置另一个策略实例
    # strategy_symbol_B = 'SIM_STOCK_B'
    # strategy_B = RealtimeSimpleMAStrategy(... signal_callback=trading_engine.handle_signal_event ...)

    # 5. 启动数据提供器和策略(们)
    print("\n启动数据提供器...")
    data_provider.start()
    
    print(f"启动策略 {strategy_symbol_A}...")
    strategy_A.start()
    # if strategy_B: strategy_B.start()

    # 6. 运行一段时间
    print(f"\n模拟运行 {run_duration_seconds} 秒...")
    time.sleep(run_duration_seconds)

    # 7. 停止所有组件
    print(f"\n{run_duration_seconds} 秒结束。停止策略...")
    strategy_A.stop()
    # if strategy_B: strategy_B.stop()
    
    print("停止数据提供器...")
    data_provider.stop()

    # 8. 输出结果
    print("\n--- 模拟结束 --- 最终结果 ---")
    print(f"最终现金: {portfolio.get_cash():.2f}")
    print("最终持仓:")
    final_holdings = portfolio.get_holdings()
    if final_holdings:
        for symbol, details in final_holdings.items():
            print(f"  {symbol}: Quantity={details['quantity']}, AvgCost={details['average_cost_price']:.2f}")
    else:
        print("  (无持仓)")
    
    # 获取最后的价格用于计算最终组合价值 (这里用provider的当前价，如果provider已停止，它们是最后生成的价格)
    # 注意: MockRealtimeDataProvider._current_prices 是内部变量，更好的方式是 provider 有一个 get_last_prices() 方法
    # 为了简单起见，我们直接访问（不推荐用于生产级代码）
    last_known_prices = data_provider._current_prices 
    final_portfolio_value = portfolio.get_total_portfolio_value(current_prices=last_known_prices)
    print(f"基于最后已知价格 {last_known_prices} 的最终组合价值: {final_portfolio_value:.2f}")
    
    print("\n交易日志:")
    trade_log = trading_engine.get_trade_log()
    if trade_log:
        for trade in trade_log:
            print(f"  {trade}")
    else:
        print("  (无交易执行)")

    print("\n完整的实时模拟交易流程测试完成。")

if __name__ == '__main__':
    main() 
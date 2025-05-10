# main.py - 主入口脚本

# 导入必要的模块
from core_engine.data_loader import load_csv_data
from strategies.simple_ma_strategy import dual_moving_average_strategy
from core_engine.backtest_engine import run_backtest
from core_engine.performance_analyzer import (
    calculate_performance_metrics,
    generate_performance_report,
    plot_portfolio_value,
    plot_strategy_on_price
)
import os # 用于创建results目录

def main():
    print("量化交易程序 - 阶段一 回测流程启动...")

    # 0. 确保results目录存在
    results_dir = "results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
        print(f"已创建目录: {results_dir}")

    # 1. 定义回测参数
    print("\n--- 1. 定义回测参数 ---")
    initial_capital = 100000.0
    data_file_path = 'data/sample_stock_data.csv' # 使用我们创建的示例数据
    # 注意: sample_stock_data.csv 中的数据非常少，均线参数需要相应调整才能产生信号
    # 例如，对于STOCK_A (5条数据), STOCK_B (3条数据)
    # 这里我们用较小的窗口期以便在示例数据上看到一些效果
    short_ma_window = 2
    long_ma_window = 3
    # 'close' 和 'symbol' 列名使用模块中的默认值

    print(f"初始资金: {initial_capital}")
    print(f"数据文件: {data_file_path}")
    print(f"短期均线窗口: {short_ma_window}, 长期均线窗口: {long_ma_window}")

    # 2. 加载数据
    print("\n--- 2. 加载数据 ---")
    ohlcv_data = load_csv_data(data_file_path)
    if ohlcv_data is None or ohlcv_data.empty:
        print("数据加载失败或数据为空，回测终止。")
        return
    print(f"成功加载 {len(ohlcv_data)} 条数据，涉及 {ohlcv_data['symbol'].nunique()} 个股票代码。")
    # print("数据预览 (前5行):\n", ohlcv_data.head())


    # 3. 生成交易信号
    print("\n--- 3. 生成交易信号 ---")
    # 注意：dual_moving_average_strategy 会在原DataFrame上添加列
    data_with_signals = dual_moving_average_strategy(
        ohlcv_data.copy(), # 传入副本以避免修改原始加载的数据
        short_window=short_ma_window,
        long_window=long_ma_window
    )
    if data_with_signals is None or data_with_signals.empty:
        print("信号生成失败或结果为空，回测终止。")
        return
    print("交易信号已生成。")
    # print("带信号的数据预览 (含'signal'列，取信号不为0的行):\n", data_with_signals[data_with_signals['signal'] != 0].head())


    # 4. 执行回测
    print("\n--- 4. 执行回测 ---")
    portfolio_history, trades = run_backtest(
        data_with_signals,
        initial_capital
    )
    if portfolio_history is None: # 即使为空DataFrame也可能返回，所以检查None
        print("回测执行失败，分析终止。")
        return
    print("回测执行完毕。")
    if portfolio_history.empty:
        print("投资组合历史为空 (可能没有交易或数据不足)。")
    # else:
        # print("投资组合历史 (后5条):\n", portfolio_history.tail())
    # if trades.empty:
        # print("交易记录为空。")
    # else:
        # print("交易记录 (前5条):\n", trades.head())

    # 5. 计算并展示绩效指标
    print("\n--- 5. 计算并展示绩效指标 ---")
    if not portfolio_history.empty:
        metrics = calculate_performance_metrics(portfolio_history, trades, initial_capital)
        performance_report_text = generate_performance_report(metrics, trades)
        print(performance_report_text)

        # 6. 绘制并保存投资组合价值图
        print("\n--- 6. 绘制投资组合价值图 ---")
        plot_title = f"Dual MA ({short_ma_window}-{long_ma_window}) Strategy Portfolio Value"
        # 确保文件名合法且路径正确
        plot_output_path = os.path.join(results_dir, f"MA_{short_ma_window}_{long_ma_window}_portfolio_value.png")
        plot_portfolio_value(portfolio_history, title=plot_title, output_path=plot_output_path)

        # 7. 绘制并保存单个股票的策略示意图 (例如 STOCK_A)
        print("\n--- 7. 绘制策略示意图 (针对特定股票) ---")
        symbol_for_strategy_plot = 'STOCK_A'
        # 检查 data_with_signals 中是否存在该股票，以及是否有足够的行来展示均线
        if symbol_for_strategy_plot in data_with_signals['symbol'].unique() and \
           len(data_with_signals[data_with_signals['symbol'] == symbol_for_strategy_plot]) >= long_ma_window :

            strategy_plot_title = f"Dual MA ({short_ma_window}-{long_ma_window}) on {symbol_for_strategy_plot}"
            strategy_plot_output_path = os.path.join(
                results_dir, 
                f"MA_{short_ma_window}_{long_ma_window}_strategy_on_{symbol_for_strategy_plot}.png"
            )
            plot_strategy_on_price(
                data_with_signals,
                symbol_to_plot=symbol_for_strategy_plot,
                title=strategy_plot_title,
                output_path=strategy_plot_output_path
            )
        else:
            print(f"无法为股票 {symbol_for_strategy_plot} 生成策略示意图：数据不足或股票不存在。")

    else:
        print("由于投资组合历史为空，无法计算绩效指标或绘制图表。")

    print("\n回测流程结束。")

if __name__ == "__main__":
    main() 
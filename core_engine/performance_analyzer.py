import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def calculate_performance_metrics(portfolio_history: pd.DataFrame, trades: pd.DataFrame, initial_capital: float):
    """
    计算回测的各项绩效指标。

    参数:
    portfolio_history (pd.DataFrame): 每日投资组合价值历史，索引为日期时间。
                                      必须包含 'total_value' 和 'returns' 列。
    trades (pd.DataFrame): 交易记录列表。
                           需要 'action' 和 'cost' 列来分析交易。
    initial_capital (float): 初始投入资金。

    返回:
    dict: 包含各项绩效指标的字典。
    """
    if portfolio_history.empty:
        return {
            "Error": "Portfolio history is empty. Cannot calculate metrics."
        }

    metrics = {}

    # 1. 总收益率
    final_value = portfolio_history['total_value'].iloc[-1]
    metrics['Total Return (%)'] = ((final_value - initial_capital) / initial_capital) * 100

    # 计算回测天数和年数
    if isinstance(portfolio_history.index, pd.DatetimeIndex):
        duration_days = (portfolio_history.index[-1] - portfolio_history.index[0]).days
        duration_years = duration_days / 365.25 if duration_days > 0 else 0
    else: # 如果索引不是DatetimeIndex，则无法精确计算年化指标
        duration_years = 0
        metrics['Warning'] = "Portfolio index is not DatetimeIndex, Annualized metrics might be inaccurate or missing."


    # 2. 年化收益率
    if duration_years > 0:
        metrics['Annualized Return (%)'] = (( (1 + metrics['Total Return (%)']/100) ** (1/duration_years) ) - 1) * 100
    else:
        metrics['Annualized Return (%)'] = "N/A (Duration < 1 year or unknown)"

    # 3. 最大回撤
    # 计算累积最高点
    cumulative_max = portfolio_history['total_value'].cummax()
    # 计算回撤百分比
    drawdown = (portfolio_history['total_value'] - cumulative_max) / cumulative_max
    metrics['Max Drawdown (%)'] = drawdown.min() * 100
    
    # 4. 夏普比率 (简化版, 无风险利率为0, 使用日收益率)
    daily_returns = portfolio_history['returns'] # 'returns' 已经是日收益率 pct_change()
    if not daily_returns.empty and daily_returns.std() != 0 and duration_years > 0:
        # 年化夏普比率 (假设一年252个交易日)
        metrics['Sharpe Ratio (Annualized)'] = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        metrics['Sharpe Ratio (Annualized)'] = "N/A"

    # 5. 交易相关统计 (如果trades DataFrame不为空)
    if trades is not None and not trades.empty:
        winning_trades = trades[trades['cost'] < 0] # 买入成本为正，卖出收益体现为负成本（即正收益）
        losing_trades = trades[trades['cost'] > 0] # 买入成本为正
        
        # 更精确的盈亏判断应基于单次完整交易（买入后卖出）
        # 这里简化为：卖出操作视为盈利（如果 proceeds > cost_basis），买入操作是成本。
        # 为了简化，我们只统计基于 'action' 的交易次数，胜率等需要更复杂的配对逻辑，暂时不实现。
        # 对于这个阶段，我们统计买卖次数
        buy_trades = trades[trades['action'] == 'BUY']
        sell_trades = trades[trades['action'] == 'SELL']
        metrics['Total Trades'] = len(trades)
        metrics['Number of Buy Trades'] = len(buy_trades)
        metrics['Number of Sell Trades'] = len(sell_trades)

        # 实际的胜率等需要跟踪每笔完整交易的盈亏，这需要将买入和卖出配对。
        # 简化：这里我们无法直接计算胜率，因为trades_log记录的是单边操作。
        # 我们可以在portfolio_history计算已实现盈亏，但那会更复杂。
        metrics['Win Rate (%)'] = "N/A (Requires trade pairing)"
        metrics['Average Win ($)'] = "N/A"
        metrics['Average Loss ($)'] = "N/A"
    else:
        metrics['Total Trades'] = 0
        metrics['Win Rate (%)'] = "N/A"

    return metrics

def generate_performance_report(metrics: dict, trades_df: pd.DataFrame = None):
    """
    生成文本格式的回测性能报告。
    """
    report = "--- Backtest Performance Report ---\n"
    for key, value in metrics.items():
        if isinstance(value, float):
            report += f"{key}: {value:.2f}\n"
        else:
            report += f"{key}: {value}\n"
    
    if trades_df is not None and not trades_df.empty:
        report += "\n--- Trades Log ---\n"
        report += trades_df.to_string()
    elif trades_df is not None and trades_df.empty:
        report += "\n--- Trades Log ---\nNo trades executed.\n"
        
    return report

def plot_portfolio_value(portfolio_history: pd.DataFrame, title: str = 'Portfolio Value Over Time', output_path: str = None):
    """
    绘制投资组合总价值随时间变化的曲线图。

    参数:
    portfolio_history (pd.DataFrame): 每日投资组合价值历史，索引为日期时间。
                                      必须包含 'total_value' 列。
    title (str): 图表标题。
    output_path (str, optional): 图片保存路径。如果提供，则保存图片。
    """
    if portfolio_history.empty or 'total_value' not in portfolio_history.columns:
        print("无法绘制投资组合价值图：数据为空或缺少 'total_value' 列。")
        return

    plt.figure(figsize=(12, 6))
    plt.plot(portfolio_history.index, portfolio_history['total_value'], label='Portfolio Value')
    
    plt.title(title)
    plt.xlabel('Date')
    plt.ylabel('Portfolio Value')
    plt.legend()
    plt.grid(True)
    
    # 格式化日期显示
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator()) # 自动选择合适的日期间隔
    plt.gcf().autofmt_xdate() # 自动旋转日期标签以防重叠

    if output_path:
        try:
            plt.savefig(output_path)
            print(f"投资组合价值图已保存到: {output_path}")
        except Exception as e:
            print(f"保存图片失败: {e}")
    else:
        plt.show() # 如果不保存，则直接显示

def plot_strategy_on_price(
    data_with_signals: pd.DataFrame,
    symbol_to_plot: str,
    title: str = 'Strategy Visualization',
    output_path: str = None,
    close_col: str = 'close',
    short_ma_col: str = 'short_ma',
    long_ma_col: str = 'long_ma',
    signal_col: str = 'signal',
    symbol_col: str = 'symbol'
):
    """
    绘制单个股票的价格、均线及买卖信号点。

    参数:
    data_with_signals (pd.DataFrame): 包含价格、均线和信号的DataFrame。
    symbol_to_plot (str): 需要绘制的股票代码。
    title (str): 图表标题。
    output_path (str, optional): 图片保存路径。
    close_col (str): 收盘价列名。
    short_ma_col (str): 短期均线列名。
    long_ma_col (str): 长期均线列名。
    signal_col (str): 交易信号列名。
    symbol_col (str): 股票代码列名。
    """
    if data_with_signals.empty or symbol_col not in data_with_signals.columns:
        print(f"无法绘制策略图：数据为空或缺少 '{symbol_col}' 列。")
        return

    stock_data = data_with_signals[data_with_signals[symbol_col] == symbol_to_plot]

    if stock_data.empty:
        print(f"无法绘制策略图：未找到股票代码 '{symbol_to_plot}' 的数据。")
        return

    fig, ax = plt.subplots(figsize=(14, 7))

    # 绘制价格和均线
    ax.plot(stock_data.index, stock_data[close_col], label=f'{symbol_to_plot} Close Price', alpha=0.7)
    if short_ma_col in stock_data.columns:
        ax.plot(stock_data.index, stock_data[short_ma_col], label=f'Short MA ({short_ma_col})', linestyle='--')
    if long_ma_col in stock_data.columns:
        ax.plot(stock_data.index, stock_data[long_ma_col], label=f'Long MA ({long_ma_col})', linestyle='--')

    # 标记买入信号
    buy_signals = stock_data[stock_data[signal_col] == 1]
    if not buy_signals.empty:
        ax.scatter(buy_signals.index, buy_signals[close_col], label='Buy Signal', marker='^', color='green', s=150, zorder=5)

    # 标记卖出信号
    sell_signals = stock_data[stock_data[signal_col] == -1]
    if not sell_signals.empty:
        ax.scatter(sell_signals.index, sell_signals[close_col], label='Sell Signal', marker='v', color='red', s=150, zorder=5)

    ax.set_title(f'{title} - {symbol_to_plot}')
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend()
    ax.grid(True)

    # 格式化日期显示
    fig.autofmt_xdate()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())

    if output_path:
        try:
            plt.savefig(output_path)
            print(f"策略示意图已保存到: {output_path}")
        except Exception as e:
            print(f"保存策略示意图失败: {e}")
    else:
        plt.show()

if __name__ == '__main__':
    # 构造与backtest_engine.py中类似的测试数据
    initial_capital_test = 10000.0
    dates_test = pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05', '2023-01-06'])
    
    portfolio_data_test = {
        'timestamp': dates_test,
        'cash': [10000, 8900, 8900, 8900, 10100, 10100], # 假设的现金流
        'holdings_value': [0, 1100, 1150, 1200, 0, 0],   # 假设的持仓价值
        'total_value': [10000, 10000, 10050, 10100, 10100, 10100] # 假设的总价值
    }
    portfolio_history_test_df = pd.DataFrame(portfolio_data_test)
    portfolio_history_test_df.set_index('timestamp', inplace=True)
    portfolio_history_test_df['returns'] = portfolio_history_test_df['total_value'].pct_change().fillna(0)

    trades_data_test = {
        'timestamp': pd.to_datetime(['2023-01-02', '2023-01-04']),
        'symbol': ['STOCK_A', 'STOCK_A'],
        'action': ['BUY', 'SELL'],
        'quantity': [100, 100],
        'price': [11, 12],
        'cost': [1100, -1200] # 买入成本为正，卖出收益（负成本）
    }
    trades_test_df = pd.DataFrame(trades_data_test)
    trades_test_df.set_index('timestamp', inplace=True)

    print("--- 测试用投资组合历史 ---")
    print(portfolio_history_test_df)
    print("\n--- 测试用交易记录 ---")
    print(trades_test_df)

    metrics_test = calculate_performance_metrics(portfolio_history_test_df, trades_test_df, initial_capital_test)
    report_test = generate_performance_report(metrics_test, trades_test_df)

    print("\n--- 性能报告 ---")
    print(report_test)

    # 测试绘图 (如果直接运行此文件，会尝试显示图片)
    plot_portfolio_value(portfolio_history_test_df, title="Test Portfolio Value", output_path="../results/test_portfolio_value.png")

    # 测试新的策略示意图函数
    strategy_plot_data = {
       'timestamp': pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05', '2023-01-06', '2023-01-07']),
       'close':   [100, 102, 101, 103, 100, 98, 100], # 调整价格使其有交叉
       'short_ma':[None, 101, 101.5, 102, 101.33, 100, 99.33],
       'long_ma': [None, None, 101, 101.66, 101.75, 101.2, 100.5],
       'signal':  [0, 0, 1, 0, -1, 0, 1], # 买入在01-03，卖出在01-05, 再买入在01-07
       'symbol':  ['TEST_STOCK'] * 7
    }
    strategy_plot_df = pd.DataFrame(strategy_plot_data).set_index('timestamp')
    plot_strategy_on_price(strategy_plot_df,
                           symbol_to_plot='TEST_STOCK',
                           title='Test Strategy Visualization (Price, MAs, Signals)',
                           output_path='../results/test_strategy_visualization.png') 
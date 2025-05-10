import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import ast
import os

# # --- BEGIN 中文字体尝试设置 --- (移除，因为将使用英文图表)
# def set_chinese_font():
#     """尝试设置matplotlib的中文字体，以便图表能正确显示中文。"""
#     try:
#         plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Microsoft YaHei', 'SimHei'] 
#         plt.rcParams['axes.unicode_minus'] = False
#     except Exception as e:
#         print(f"警告：自动设置中文字体失败。图表中的中文可能无法正确显示。错误：{e}")
# # --- END 中文字体尝试设置 ---

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
            "错误": "投资组合历史为空，无法计算指标。"
        }

    metrics = {}

    # 1. 总收益率
    final_value = portfolio_history['total_value'].iloc[-1]
    metrics['总收益率 (%)'] = ((final_value - initial_capital) / initial_capital) * 100

    # 计算回测天数和年数
    if isinstance(portfolio_history.index, pd.DatetimeIndex):
        duration_days = (portfolio_history.index[-1] - portfolio_history.index[0]).days
        duration_years = duration_days / 365.25 if duration_days > 0 else 0
    else: # 如果索引不是DatetimeIndex，则无法精确计算年化指标
        duration_years = 0
        metrics['警告'] = "投资组合索引不是日期时间类型，年化指标可能不准确或缺失。"


    # 2. 年化收益率
    if duration_years > 0:
        metrics['年化收益率 (%)'] = (( (1 + metrics['总收益率 (%)']/100) ** (1/duration_years) ) - 1) * 100
    else:
        metrics['年化收益率 (%)'] = "N/A (期限小于一年或未知)"

    # 3. 最大回撤
    # 计算累积最高点
    cumulative_max = portfolio_history['total_value'].cummax()
    # 计算回撤百分比
    drawdown = (portfolio_history['total_value'] - cumulative_max) / cumulative_max
    metrics['最大回撤 (%)'] = drawdown.min() * 100
    
    # 4. 夏普比率 (简化版, 无风险利率为0, 使用日收益率)
    daily_returns = portfolio_history['returns'] # 'returns' 已经是日收益率 pct_change()
    if not daily_returns.empty and daily_returns.std() != 0 and duration_years > 0:
        # 年化夏普比率 (假设一年252个交易日)
        metrics['夏普比率 (年化)'] = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        metrics['夏普比率 (年化)'] = "N/A"

    # 5. 交易相关统计 (如果trades DataFrame不为空)
    if trades is not None and not trades.empty:
        buy_trades = trades[trades['action'] == 'BUY']
        sell_trades = trades[trades['action'] == 'SELL']
        metrics['总交易次数'] = len(trades)
        metrics['买入次数'] = len(buy_trades)
        metrics['卖出次数'] = len(sell_trades)

        metrics['胜率 (%)'] = "N/A (需交易配对)"
        metrics['平均盈利 ($)'] = "N/A (需交易配对)"
        metrics['平均亏损 ($)'] = "N/A (需交易配对)"
    else:
        metrics['总交易次数'] = 0
        metrics['胜率 (%)'] = "N/A"
        metrics['平均盈利 ($)'] = "N/A"
        metrics['平均亏损 ($)'] = "N/A"


    return metrics

def generate_performance_report(metrics: dict, 
                                trades_df: pd.DataFrame = None, 
                                title: str = None,
                                commission_rate_pct: float = None, # 新增手续费率参数
                                min_commission: float = None):    # 新增最低手续费参数
    """
    生成文本格式的回测性能报告。
    新增显示手续费设置的功能。
    """
    if title:
        report = f"--- {title} ---\n"
    else:
        report = "--- 回测性能报告 ---\n"
    
    # 在指标前显示手续费信息 (如果提供了)
    if commission_rate_pct is not None and min_commission is not None:
        report += f"手续费设置: 费率={commission_rate_pct*100:.4f}%, 最低收费={min_commission:.2f}元/笔\n"
        report += "---\n" # 分隔线
        
    for key, value in metrics.items():
        if isinstance(value, float):
            report += f"{key}: {value:.2f}\n"
        else:
            report += f"{key}: {value}\n"
    
    if trades_df is not None and not trades_df.empty:
        report += "\n--- 交易记录 ---\n"
        report += trades_df.to_string()
    elif trades_df is not None and trades_df.empty:
        report += "\n--- 交易记录 ---\n没有执行任何交易。\n"
        
    return report

def plot_portfolio_value(portfolio_history: pd.DataFrame, title: str = 'Portfolio Value Over Time', output_path: str = None):
    """
    绘制投资组合总价值随时间变化的曲线图。
    """
    # set_chinese_font() # 移除
    if portfolio_history.empty or 'total_value' not in portfolio_history.columns:
        print("Cannot plot portfolio value: Data is empty or missing 'total_value' column.")
        return

    fig = plt.figure(figsize=(12, 6)) # Capture the figure object
    plt.plot(portfolio_history.index, portfolio_history['total_value'], label='Portfolio Value')
    
    plt.title(title) # Title is passed from main.py, ensure it's English there too
    plt.xlabel('Date')
    plt.ylabel('Portfolio Value')
    plt.legend()
    plt.grid(True)
    
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.gcf().autofmt_xdate()

    if output_path:
        try:
            plt.savefig(output_path)
            print(f"Portfolio value chart saved to: {output_path}")
            plt.close(fig) # Close the figure after saving
        except Exception as e:
            print(f"Failed to save portfolio value chart: {e}")
    else:
        plt.show()

def plot_strategy_on_price(
    data_with_signals: pd.DataFrame,
    symbol_to_plot: str,
    indicator_cols: list = None,
    strategy_name: str = '',
    title: str = 'Strategy Visualization', # Default title in English
    output_path: str = None,
    close_col: str = 'close',
    signal_col: str = 'signal',
    symbol_col: str = 'symbol'
):
    """
    绘制单个股票的价格、指定指标及买卖信号点。
    """
    # set_chinese_font() # 移除
    if data_with_signals.empty or symbol_col not in data_with_signals.columns:
        print(f"Cannot plot strategy: Data is empty or missing '{symbol_col}' column.")
        return

    stock_data = data_with_signals[data_with_signals[symbol_col] == symbol_to_plot]

    if stock_data.empty:
        print(f"Cannot plot strategy: Data for symbol '{symbol_to_plot}' not found.")
        return

    fig, ax = plt.subplots(figsize=(14, 7))

    ax.plot(stock_data.index, stock_data[close_col], label=f'{symbol_to_plot} {close_col.capitalize()}', alpha=0.9, color='black')

    if indicator_cols:
        for i, indicator_name in enumerate(indicator_cols):
            if indicator_name in stock_data.columns:
                ax.plot(stock_data.index, stock_data[indicator_name], 
                        label=f'{indicator_name.upper()} ({strategy_name})', linestyle='--', alpha=0.7)
            else:
                print(f"Warning: Indicator column '{indicator_name}' not found in data, cannot plot.")

    buy_signals = stock_data[stock_data[signal_col] == 1]
    if not buy_signals.empty:
        ax.scatter(buy_signals.index, buy_signals[close_col], label='Buy Signal', marker='^', color='green', s=150, zorder=5)

    sell_signals = stock_data[stock_data[signal_col] == -1]
    if not sell_signals.empty:
        ax.scatter(sell_signals.index, sell_signals[close_col], label='Sell Signal', marker='v', color='red', s=150, zorder=5)

    ax.set_title(title) # Title is passed from main.py, ensure it's English there
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend()
    ax.grid(True)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()

    if output_path:
        try:
            plt.savefig(output_path)
            print(f"Strategy chart saved to: {output_path}")
            plt.close(fig) # Close the figure after saving
        except Exception as e:
            print(f"Failed to save strategy chart: {e}")
    else:
        plt.show()

def plot_parameter_impact(
    summary_df: pd.DataFrame, 
    target_symbol: str, 
    parameter_to_plot: str, 
    metric_to_plot: str = '夏普比率',
    output_dir: str = 'results',
    other_params_to_fix: dict = None # 可选，用于固定其他参数的值进行筛选
):
    """
    绘制单个参数对指定性能指标影响的图表。
    例如，绘制 'period' 对 '夏普比率' 的影响。

    参数:
    summary_df (pd.DataFrame): 包含所有回测运行总结的DataFrame。
                                必须包含 '股票代码', '参数', 和 metric_to_plot 列。
    target_symbol (str): 要绘制图表的目标股票代码。
    parameter_to_plot (str): 要作为X轴的参数名称 (例如 'period')。
    metric_to_plot (str): 要作为Y轴的性能指标名称 (例如 '夏普比率')。
    output_dir (str): 图表保存目录。
    other_params_to_fix (dict): 可选字典，用于固定其他参数的值。 
                                  例如 {'oversold_threshold': 30, 'overbought_threshold': 70}
                                  如果为None，则对其他参数的所有组合取平均值。
    """
    if summary_df.empty:
        print(f"plot_parameter_impact: summary_df 为空，无法绘图。")
        return

    if '参数' not in summary_df.columns or '股票代码' not in summary_df.columns or metric_to_plot not in summary_df.columns:
        print(f"plot_parameter_impact: summary_df 缺少必要的列 ('股票代码', '参数', '{metric_to_plot}')")
        return

    # 复制DataFrame以避免修改原始数据
    df_to_plot = summary_df.copy()

    # 1. 解析'参数'列字符串为字典，并提取各参数为新列
    try:
        # 先尝试获取所有参数名，假设所有参数字典结构一致
        sample_params_dict = ast.literal_eval(df_to_plot['参数'].iloc[0])
        param_keys = list(sample_params_dict.keys())
        
        for key in param_keys:
            df_to_plot[f'param_{key}'] = df_to_plot['参数'].apply(lambda x: ast.literal_eval(x).get(key))
    except Exception as e:
        print(f"plot_parameter_impact: 解析'参数'列失败: {e}。请确保参数列是有效的字典字符串。")
        return

    # 2. 筛选目标股票
    df_symbol = df_to_plot[df_to_plot['股票代码'] == target_symbol].copy()
    if df_symbol.empty:
        print(f"plot_parameter_impact: 未找到股票代码 '{target_symbol}' 的数据。")
        return

    # 3. 转换指标列为数值型，无效值转为NaN
    df_symbol[metric_to_plot] = pd.to_numeric(df_symbol[metric_to_plot], errors='coerce')
    df_symbol.dropna(subset=[metric_to_plot], inplace=True) # 移除无法转换为数值的行

    # 检查 parameter_to_plot 是否存在于解析后的列中
    col_to_group_by = f'param_{parameter_to_plot}'
    if col_to_group_by not in df_symbol.columns:
        print(f"plot_parameter_impact: 参数 '{parameter_to_plot}' (作为 '{col_to_group_by}') 在解析后未找到。")
        return

    # 4. (可选) 固定其他参数
    fixed_params_str_part = "all_others_averaged"
    if other_params_to_fix and isinstance(other_params_to_fix, dict):
        conditions = []
        fixed_params_str_parts_list = []
        for p_name, p_val in other_params_to_fix.items():
            parsed_col_name = f'param_{p_name}'
            if parsed_col_name in df_symbol.columns:
                df_symbol = df_symbol[df_symbol[parsed_col_name] == p_val]
                fixed_params_str_parts_list.append(f"{p_name}{p_val}")
            else:
                print(f"plot_parameter_impact: 尝试固定参数 '{p_name}' 但未在数据中找到解析列 '{parsed_col_name}'")
        if not df_symbol.empty and fixed_params_str_parts_list:
            fixed_params_str_part = "fixed_" + "_".join(fixed_params_str_parts_list)
        elif df_symbol.empty:
            print(f"plot_parameter_impact: 在固定参数 {other_params_to_fix} 后没有剩余数据。")
            return
            
    # 5. 按目标参数分组并计算指标的平均值
    # 如果没有固定其他参数 (other_params_to_fix is None)，则这里会对其他参数的不同组合取平均
    grouped_data = df_symbol.groupby(col_to_group_by)[metric_to_plot].mean().reset_index()

    if grouped_data.empty:
        print(f"plot_parameter_impact: 分组后数据为空 (股票: {target_symbol}, 参数: {parameter_to_plot})。无法绘图。")
        return

    # 6. 绘图
    plt.figure(figsize=(10, 6))
    plt.plot(grouped_data[col_to_group_by], grouped_data[metric_to_plot], marker='o', linestyle='-')
    
    metric_safe_name_for_plot = _get_metric_safe_name(metric_to_plot)

    title_str = f'{metric_safe_name_for_plot} vs. {parameter_to_plot} for {target_symbol}'
    if other_params_to_fix:
        title_str += f" (Fixed: {other_params_to_fix})"
    else:
        title_str += f" (Averaged over other params)"
    plt.title(title_str)
    plt.xlabel(parameter_to_plot)
    plt.ylabel(f'Average {metric_safe_name_for_plot}')
    plt.grid(True)
    plt.tight_layout()

    # 7. 保存图表
    plot_filename = f"param_impact_{metric_safe_name_for_plot}_vs_{parameter_to_plot}_for_{target_symbol}_{fixed_params_str_part}.png"
    plot_output_path = os.path.join(output_dir, plot_filename)
    try:
        plt.savefig(plot_output_path)
        print(f"Parameter impact chart saved to: {plot_output_path}")
    except Exception as e:
        print(f"Failed to save parameter impact chart: {e}")
    plt.close() # 关闭图形，避免在循环中打开过多窗口

# Helper function to get English safe names for metrics used in plots
def _get_metric_safe_name(metric_name_cn: str) -> str:
    mapping = {
        "夏普比率": "SharpeRatio",
        "总回报率(%)": "TotalReturnPct",
        "最大回撤(%)": "MaxDrawdownPct",
        "年化回报率(%)": "AnnualizedReturnPct",
        # 可以根据需要添加更多映射
    }
    # 替换掉特殊字符，以防原始metric_name_cn不在mapping中但仍用于文件名
    safe_fallback_name = metric_name_cn.replace('(%','Pct').replace('(','').replace(')','').replace(' ','_').replace('/','_').replace('%','Pct')
    return mapping.get(metric_name_cn, safe_fallback_name) # 如果找不到映射，返回处理过的原名（可能仍含中文）

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
    # 模拟手续费信息传递给报告生成器
    report_test = generate_performance_report(metrics_test, trades_test_df, 
                                              title="测试性能报告 (含手续费信息)",
                                              commission_rate_pct=0.0005, 
                                              min_commission=5.0)

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

    # --- 测试 plot_parameter_impact ---
    print("\n--- 测试参数影响图绘制 ---")
    # 构造一个模拟的 summary_df
    sample_summary_data = {
        '股票代码': ['MSFT', 'MSFT', 'MSFT', 'MSFT', 'MSFT', 'MSFT', 'AAPL', 'AAPL'],
        '参数': [
            str({'period': 10, 'threshold': 20}), str({'period': 10, 'threshold': 30}),
            str({'period': 14, 'threshold': 20}), str({'period': 14, 'threshold': 30}),
            str({'period': 20, 'threshold': 20}), str({'period': 20, 'threshold': 30}),
            str({'period': 10, 'threshold': 25}), str({'period': 14, 'threshold': 25})
        ],
        '夏普比率': [-0.5, -0.2, 0.1, 0.3, -0.1, 0.0, -0.4, 0.2],
        '总回报率(%)': [1.0, 2.0, 3.0, 5.0, 0.5, 1.5, 0.8, 2.5]
    }
    test_summary_df = pd.DataFrame(sample_summary_data)
    os.makedirs("results", exist_ok=True) #确保目录存在

    plot_parameter_impact(test_summary_df, target_symbol='MSFT', parameter_to_plot='period', metric_to_plot='夏普比率', output_dir='results')
    plot_parameter_impact(test_summary_df, target_symbol='MSFT', parameter_to_plot='threshold', metric_to_plot='夏普比率', output_dir='results')
    plot_parameter_impact(test_summary_df, target_symbol='AAPL', parameter_to_plot='period', metric_to_plot='总回报率(%)', output_dir='results')
    # 测试固定其他参数
    plot_parameter_impact(test_summary_df, target_symbol='MSFT', parameter_to_plot='period', metric_to_plot='夏普比率', output_dir='results', other_params_to_fix={'threshold': 20}) 
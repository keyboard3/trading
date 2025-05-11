import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import ast
import os
import re # Ensure re is imported for _get_metric_safe_name and _get_safe_filename_part

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
                                commission_rate_pct: float = None, 
                                min_commission: float = None,
                                slippage_pct: float = None): # 新增滑点参数
    """
    生成文本格式的回测性能报告。
    新增显示手续费和滑点设置的功能。
    """
    if title:
        report = f"--- {title} ---\n"
    else:
        report = "--- 回测性能报告 ---\n"
    
    # 在指标前显示交易条件信息
    has_trading_conditions = False
    trading_conditions_report = ""
    if commission_rate_pct is not None and min_commission is not None:
        trading_conditions_report += f"手续费设置: 费率={commission_rate_pct*100:.4f}%, 最低收费={min_commission:.2f}元/笔\n"
        has_trading_conditions = True
    
    if slippage_pct is not None and slippage_pct > 0:
        trading_conditions_report += f"滑点设置: {slippage_pct*100:.4f}%\n"
        has_trading_conditions = True

    if has_trading_conditions:
        report += trading_conditions_report
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
    # set_chinese_font() has been removed
    if portfolio_history.empty or 'total_value' not in portfolio_history.columns:
        print("Cannot plot portfolio value: Data is empty or missing 'total_value' column.")
        print("绘图失败：投资组合历史数据为空或缺少 'total_value' 列。")
        return

    fig = plt.figure(figsize=(12, 6)) # Capture the figure object
    plt.plot(portfolio_history.index, portfolio_history['total_value'], label='Portfolio Value')
    
    plt.title(title) # Title is passed from main.py, ensure it's English there
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
            print(f"保存投资组合价值图表失败: {e}")
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
    # set_chinese_font() has been removed
    if data_with_signals.empty or symbol_col not in data_with_signals.columns:
        print(f"Cannot plot strategy: Data is empty or missing '{symbol_col}' column.")
        print(f"绘图失败：策略数据为空或缺少 '{symbol_col}' 列。")
        return

    stock_data = data_with_signals[data_with_signals[symbol_col] == symbol_to_plot]

    if stock_data.empty:
        print(f"Cannot plot strategy: Data for symbol '{symbol_to_plot}' not found.")
        print(f"绘图失败：未找到股票代码 '{symbol_to_plot}' 的数据。")
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
                print(f"警告：指标列 '{indicator_name}' 在数据中未找到，无法绘制。")

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
            print(f"保存策略图表失败: {e}")
    else:
        plt.show()

def plot_parameter_impact(
    results_df: pd.DataFrame, 
    parameters_to_plot: list, # Changed from parameter_to_plot: str
    metric_to_plot: str = '夏普比率',
    output_dir: str = 'results',
    other_params_to_fix: dict = None, # Optional, to fix other parameter values
    strategy_name: str = 'Strategy' # Added strategy_name for context in title/filename
):
    """
    绘制多个参数各自对指定性能指标影响的图表。
    为 parameters_to_plot 中的每个参数生成一个图。

    参数:
    results_df (pd.DataFrame): 包含所有回测运行总结的DataFrame。
                               各参数应为独立列，指标列也应存在且为数值型。
                               必须包含 '股票代码' (即使未使用，保持兼容性或未来使用), 
                               以及 metric_to_plot 和 parameters_to_plot 中的所有参数列。
    parameters_to_plot (list): 要作为X轴的参数名称列表 (例如 ['period', 'oversold_threshold'])。
    metric_to_plot (str): 要作为Y轴的性能指标名称 (例如 '夏普比率')。
    output_dir (str): 图表保存目录。
    other_params_to_fix (dict): 可选字典，用于固定其他参数的值。
                                  例如 {'oversold_threshold': 30}
                                  如果为None，则对其他参数的所有组合取平均值。
    strategy_name (str): 策略名称，用于图表标题和文件名。
    """
    if results_df.empty:
        print(f"plot_parameter_impact: results_df 为空，无法绘图。")
        return

    required_cols = parameters_to_plot + [metric_to_plot]
    if not all(col in results_df.columns for col in required_cols):
        missing_cols = [col for col in required_cols if col not in results_df.columns]
        print(f"plot_parameter_impact: results_df 缺少必需的列: {missing_cols}。无法绘图。")
        return

    # Ensure the metric column is numeric
    if not pd.api.types.is_numeric_dtype(results_df[metric_to_plot]):
        print(f"plot_parameter_impact: 指标列 '{metric_to_plot}' 不是数值类型，尝试转换...")
        results_df[metric_to_plot] = pd.to_numeric(results_df[metric_to_plot], errors='coerce')
        if results_df[metric_to_plot].isnull().all():
            print(f"plot_parameter_impact: 指标列 '{metric_to_plot}' 转换后全为NaN，无法绘图。")
            return
    
    # Outer loop for each parameter to plot
    for param_key_to_plot in parameters_to_plot:
        print(f"\n--- 生成参数 '{param_key_to_plot}' 对 '{metric_to_plot}' 的影响图 ---")
        
        current_results_df = results_df.copy()

        # Apply other_params_to_fix if provided
        fixed_params_title_part = ""
        if other_params_to_fix:
            temp_fixed_parts = []
            for fixed_key, fixed_value in other_params_to_fix.items():
                if fixed_key == param_key_to_plot: # Cannot fix the parameter being plotted
                    continue
                if fixed_key in current_results_df.columns:
                    current_results_df = current_results_df[current_results_df[fixed_key] == fixed_value]
                    temp_fixed_parts.append(f"{_get_plot_friendly_param_name(fixed_key)}={fixed_value}")
                else:
                    print(f"警告: 要固定的参数 '{fixed_key}' 不在结果列中，已忽略。")
            if temp_fixed_parts:
                fixed_params_title_part = " (Fixed: " + ", ".join(temp_fixed_parts) + ")"
        
        if current_results_df.empty:
            print(f"在为 '{param_key_to_plot}' 固定参数 {other_params_to_fix} 后，没有数据可供绘图。")
            continue

        if param_key_to_plot not in current_results_df.columns:
            print(f"错误: 参数 '{param_key_to_plot}' 不在提供的DataFrame列中。跳过此参数。")
            continue

        # Group by the parameter to plot and calculate mean of the metric
        # Ensure the parameter column is not all NaN before grouping, also drop NaN metrics for this param
        plot_data = current_results_df.dropna(subset=[param_key_to_plot, metric_to_plot])
        if plot_data.empty:
            print(f"在移除 '{param_key_to_plot}' 或 '{metric_to_plot}' 的NaN值后，没有数据可供绘图。")
            continue
            
        # Convert param_key_to_plot to numeric if it looks like numbers, to ensure correct sorting/plotting
        # This helps if a parameter like 'window' is stored as object/string but should be numeric on axis
        if pd.api.types.is_object_dtype(plot_data[param_key_to_plot]):
            try:
                plot_data[param_key_to_plot] = pd.to_numeric(plot_data[param_key_to_plot])
            except ValueError:
                print(f"参数列 '{param_key_to_plot}' 包含非数值，将按原样处理 (可能导致排序或绘图问题)。")
        
        # Group data and calculate mean metric
        grouped_data = plot_data.groupby(param_key_to_plot)[metric_to_plot].mean().sort_index()

        if grouped_data.empty:
            print(f"按 '{param_key_to_plot}' 分组并计算 '{metric_to_plot}' 平均值后无数据。")
            continue

        fig, ax = plt.subplots(figsize=(10, 6))

        # Decide plot type based on number of unique values or data type
        if pd.api.types.is_numeric_dtype(grouped_data.index) and grouped_data.nunique() > 1:
            grouped_data.plot(kind='line', marker='o', ax=ax)
            ax.set_ylabel(f"Average {_get_english_display_metric_name(metric_to_plot)}")
        else: # Categorical or few points - use bar chart
            grouped_data.plot(kind='bar', ax=ax)
            ax.set_ylabel(f"Average {_get_english_display_metric_name(metric_to_plot)}")
            plt.xticks(rotation=45, ha='right')

        plot_friendly_param_name = _get_plot_friendly_param_name(param_key_to_plot)
        title = f'{strategy_name}: {plot_friendly_param_name} vs {_get_english_display_metric_name(metric_to_plot)}{fixed_params_title_part}'
        ax.set_title(title)
        ax.set_xlabel(plot_friendly_param_name)
        plt.tight_layout()
        plt.grid(True, linestyle='--', alpha=0.7)

        # Sanitize file names
        safe_param_name = _get_safe_filename_part(param_key_to_plot)
        safe_metric_name = _get_metric_safe_name(metric_to_plot)
        safe_strategy_name = _get_safe_filename_part(strategy_name)
        fixed_params_filename_part = _get_safe_filename_part(fixed_params_title_part.replace("Fixed:", "fixed").replace(" ", ""))

        plot_filename = f"param_impact_{safe_strategy_name}_{safe_param_name}_vs_{safe_metric_name}{fixed_params_filename_part}.png"
        output_file_path = os.path.join(output_dir, plot_filename)

        try:
            plt.savefig(output_file_path)
            print(f"参数影响图已保存到: {output_file_path}")
        except Exception as e:
            print(f"保存参数影响图失败: {e}")
        finally:
            plt.close(fig)

def _get_english_display_metric_name(metric_name_cn: str) -> str:
    """将中文指标名转换为图表上显示的英文名称。"""
    mapping = {
        "夏普比率": "Sharpe Ratio",
        "总回报率": "Total Return", # As per main.py's metrics_for_impact_charts
        "最大回撤": "Max Drawdown", # As per main.py
        "胜率": "Win Rate",         # As per main.py
        # More comprehensive mapping for robustness if main.py changes or other sources call this
        "总回报率(%)": "Total Return (%)",
        "总收益率 (%)": "Total Return (%)", # From calculate_performance_metrics
        "夏普比率 (年化)": "Sharpe Ratio (Annualized)",
        "最大回撤(%)": "Max Drawdown (%)",
        "年化回报率(%)": "Annualized Return (%)",
        "年化收益率 (%)": "Annualized Return (%)",
        "胜率 (%)": "Win Rate (%)"
    }
    # Fallback to a cleaned-up version of the original name if not in mapping
    return mapping.get(metric_name_cn, metric_name_cn.replace('(%)','(Pct)').replace(' ','_').replace('（','(').replace('）',')'))

def _get_metric_safe_name(metric_name_cn: str) -> str:
    """将中文指标名映射为纯英文的、适合文件名的安全字符串。"""
    mapping = {
        "夏普比率": "SharpeRatio",
        "总回报率": "TotalReturn",
        "最大回撤": "MaxDrawdown",
        "胜率": "WinRate",
        # More comprehensive mapping from existing and calculate_performance_metrics
        "总回报率(%)": "TotalReturnPct",
        "总收益率 (%)": "TotalReturnPct",
        "最大回撤(%)": "MaxDrawdownPct",
        "年化回报率(%)": "AnnualizedReturnPct",
        "年化收益率 (%)": "AnnualizedReturnPct",
        "夏普比率 (年化)": "SharpeRatioAnnualized", # Differentiate from simple "SharpeRatio" if needed
        "胜率 (%)": "WinRatePct"
    }
    raw_name = mapping.get(metric_name_cn, metric_name_cn)
    # Basic ASCII conversion: replace problematic chars, then keep only alphanumeric, underscore, hyphen
    safe_name = raw_name.replace('(%)','Pct').replace('(','').replace(')','').replace(' ','_').replace('/','_').replace('%','Pct')
    safe_name = safe_name.replace('（','(').replace('）',')') # Normalize parentheses before stripping
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', safe_name)
    if not safe_name: # if all chars were non-alphanumeric
        safe_name = "metric" 
    return safe_name

def _get_plot_friendly_param_name(param_name: str) -> str:
    return ' '.join(word.capitalize() for word in param_name.split('_'))

# Helper function for sanitizing parts of filenames
def _get_safe_filename_part(name_part: str) -> str:
    """Converts a string part into a safe version for filenames."""
    if not isinstance(name_part, str):
        name_part = str(name_part)
    # Remove or replace characters not typically allowed or problematic in filenames
    name_part = name_part.replace(' ', '_').replace('(', '').replace(')', '').replace('[', '').replace(']', '')
    name_part = name_part.replace('%', 'pct').replace('/', '-').replace(':', '-').replace('=', '') # Added = removal
    # Remove any sequence of non-alphanumeric characters (except underscore and hyphen)
    name_part = re.sub(r'[^a-zA-Z0-9_-]', '', name_part)
    return name_part.lower()

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
    plot_portfolio_value(portfolio_history_test_df, title="Test Portfolio Value (EN)", output_path="../results/test_portfolio_value.png")

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
                           indicator_cols=['short_ma', 'long_ma'],
                           strategy_name='MA_Test',
                           title='Test Strategy Visualization (Price, MAs, Signals) (EN)',
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
        '总回报率(%)': [1.0, 2.0, 3.0, 5.0, 0.5, 1.5, 0.8, 2.5],
        # Add a column that main.py might use for metric_to_plot like '总回报率' without (%)
        '总回报率': [1.0, 2.0, 3.0, 5.0, 0.5, 1.5, 0.8, 2.5],
        '最大回撤': [-10.0, -5.0, -2.0, -1.0, -15.0, -8.0, -12.0, -3.0]
    }
    test_summary_df = pd.DataFrame(sample_summary_data)
    # Expand params for test_summary_df to match how plot_parameter_impact expects it (params as columns)
    test_summary_df['params_dict'] = test_summary_df['参数'].apply(ast.literal_eval)
    params_expanded = pd.json_normalize(test_summary_df['params_dict'])
    for col in params_expanded.columns: # Ensure param columns are added
        test_summary_df[col] = params_expanded[col]

    os.makedirs("results", exist_ok=True) #确保目录存在

    # Test with a metric name that's in metrics_for_impact_charts from main.py
    plot_parameter_impact(test_summary_df.copy(), strategy_name="TestRSI", parameters_to_plot=['period', 'threshold'], metric_to_plot='夏普比率', output_dir='results')
    plot_parameter_impact(test_summary_df.copy(), strategy_name="TestRSI", parameters_to_plot=['period', 'threshold'], metric_to_plot='总回报率', output_dir='results') # Test '总回报率'
    # 测试固定其他参数
    plot_parameter_impact(test_summary_df.copy(), strategy_name="TestRSI", parameters_to_plot=['period'], metric_to_plot='夏普比率', output_dir='results', other_params_to_fix={'threshold': 20})
    plot_parameter_impact(test_summary_df.copy(), strategy_name="TestRSI", parameters_to_plot=['threshold'], metric_to_plot='最大回撤', output_dir='results', other_params_to_fix={'period': 14}) 
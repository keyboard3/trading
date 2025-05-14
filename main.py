# main.py - 主入口脚本

# 导入必要的模块
from core_engine.data_loader import init_db, load_data_from_db, DB_FILE, OHLCV_DAILY_TABLE_NAME, OHLCV_MINUTE_TABLE_NAME, import_csv_to_db, DATA_DIR # Updated import
from core_engine.backtest_engine import run_backtest
from core_engine.performance_analyzer import (
    calculate_performance_metrics,
    generate_performance_report,
    plot_portfolio_value,
    plot_strategy_on_price,
    plot_parameter_impact # <<< 新增导入
)
import os # 用于创建results目录 和 检查文件路径
import sys # 用于退出程序
import pandas as pd # 用于创建汇总DataFrame
import itertools # <<< 导入itertools用于生成参数组合
import shutil # <<< 新增导入 shutil 用于删除目录树
import ast # 用于安全地评估字符串为Python对象
import importlib # <<< 新增导入 importlib

# --- 策略配置 --- 
# 用户可以在这里选择要运行的策略和配置其参数
# SELECTED_STRATEGY = 'MA'  # 可选: 'MA' (双均线), 'RSI'
SELECTED_STRATEGY = 'RSI' # <--- 修改这里来选择策略 (或者 'MA')

# --- 参数优化开关 ---
PERFORM_OPTIMIZATION = True # 设置为True以运行参数优化，False则运行单次回测使用下方默认参数

STRATEGY_CONFIG = {
    'MA': {
        # 'function': dual_moving_average_strategy, # 改为函数名字符串
        'module_name': 'strategies.simple_ma_strategy',
        'function_name': 'dual_moving_average_strategy',
        'short_window': 20, 
        'long_window': 50,
        'param_grid': { # 示例MA参数网格 (当前未启用优化，但结构备用)
            'short_window': [10, 20],
            'long_window': [30, 50, 60]
        },
        'indicator_cols': ['short_ma', 'long_ma'] # 新增，用于绘图
    },
    'RSI': {
        # 'function': rsi_strategy, # 改为函数名字符串
        'module_name': 'strategies.rsi_strategy',
        'function_name': 'rsi_strategy',
        'period': 14,
        'oversold_threshold': 30,
        'overbought_threshold': 70,
        'param_grid': { # 新增RSI参数网格定义
            'period': [14, 20],
            'oversold_threshold': [25, 30],
            'overbought_threshold': [70, 75]
        },
        'indicator_cols': ['rsi'] # 新增，用于绘图
    }
}

# --- 回测参数 ---
INITIAL_CAPITAL = 100000.0
# 选择要回测的股票代码列表，确保数据库中有这些代码的数据
# SYMBOLS_TO_BACKTEST = ['STOCK_A', 'STOCK_B'] # 用于示例CSV数据时的符号
SYMBOLS_TO_BACKTEST = ['MSFT']       # <--- 修改：只回测一个股票
# SYMBOLS_TO_BACKTEST = ['STOCK_A'] # 测试单个股票

# --- 数据时间范围 (可选，如果为None，则加载数据库中该symbol的所有数据) ---
# START_DATE = '2023-01-01' # 示例
# END_DATE = '2023-12-31'   # 示例
START_DATE = None # 使用数据库中最早的日期
END_DATE = None   # 使用数据库中最新的日期

# --- 交易成本参数 ---
COMMISSION_RATE_PCT = 0.0005 # 万分之五 (0.05%)
MIN_COMMISSION_PER_TRADE = 5.0   # 最低手续费5元
DEFAULT_SLIPPAGE_PCT = 0.0001 # 默认滑点百分比: 0.01% (万分之一)

RESULTS_DIR = "results" # 顶层结果目录
CURRENT_RUN_TAG = "Phase3_UI_Dev_Data" # <<< 更新：反映当前为阶段三UI开发准备数据

def get_strategy_function(module_name: str, function_name: str):
    """动态导入并返回策略函数。"""
    try:
        module = importlib.import_module(module_name)
        return getattr(module, function_name)
    except ImportError:
        print(f"错误：无法导入策略模块 '{module_name}'。")
        return None
    except AttributeError:
        print(f"错误：在模块 '{module_name}' 中未找到策略函数 '{function_name}'。")
        return None

def execute_single_backtest_run(
    symbol: str,
    strategy_id: str, # 例如 'RSI'
    strategy_specific_params: dict, # 例如 {'period': 14, ...}
    selected_strategy_config: dict, # STRATEGY_CONFIG[strategy_id] 的内容
    results_output_dir: str, # 结果保存的特定目录
    start_date: str = None, # 使用全局默认值或API提供的值
    end_date: str = None,
    initial_capital: float = INITIAL_CAPITAL,
    commission_rate_pct: float = COMMISSION_RATE_PCT,
    min_commission_per_trade: float = MIN_COMMISSION_PER_TRADE,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT # 新增滑点参数
) -> dict:
    """
    执行单次回测（单个股票，单个参数集），并返回结果。
    """
    print(f"\n\n{'='*20} 开始执行单次回测: {strategy_id} on {symbol} with {strategy_specific_params} {'='*20}")
    print(f"结果将保存到: {results_output_dir}")

    # 初始化返回字典
    run_result = {
        "metrics": None,
        "report_path": None,
        "portfolio_value_chart_path": None,
        "strategy_chart_path": None,
        "error": None
    }

    strategy_function = get_strategy_function(
        selected_strategy_config['module_name'], 
        selected_strategy_config['function_name']
    )
    if not strategy_function:
        run_result["error"] = f"无法加载策略函数 {selected_strategy_config['module_name']}.{selected_strategy_config['function_name']}"
        return run_result

    # 1. 加载数据
    print(f"\n--- 1.1 为 {symbol} 加载数据 ---")
    market_data_for_symbol = load_data_from_db(symbols=[symbol], start_date=start_date, end_date=end_date)
    if market_data_for_symbol is None or market_data_for_symbol.empty:
        error_msg = f"数据库中未找到股票 {symbol} 的数据。"
        print(error_msg)
        run_result["error"] = error_msg
        return run_result
    print(f"成功为 {symbol} 从数据库加载 {len(market_data_for_symbol)} 条数据。")

    # 2. 生成信号
    print(f"\n--- 1.2 为 {symbol} 生成交易信号 ({strategy_id}策略) ---")
    data_with_signals = strategy_function(
        market_data_for_symbol.copy(),
        **strategy_specific_params
    )
    if data_with_signals is None or data_with_signals.empty or 'signal' not in data_with_signals.columns:
        error_msg = f"为 {symbol} 生成信号失败或结果为空/不含signal列。"
        print(error_msg)
        run_result["error"] = error_msg
        return run_result
    print(f"股票 {symbol} 的交易信号已生成。")

    # 3. 执行回测
    print(f"\n--- 1.3 为 {symbol} 执行回测 ---")
    portfolio_history, trades = run_backtest(
        data_with_signals,
        initial_capital,
        commission_rate_pct=commission_rate_pct,
        min_commission=min_commission_per_trade,
        slippage_pct=slippage_pct # 传递滑点参数
    )
    if portfolio_history is None:
        error_msg = f"为 {symbol} 执行回测失败。"
        print(error_msg)
        run_result["error"] = error_msg
        return run_result
    print(f"股票 {symbol} 的回测执行完毕。")

    if portfolio_history.empty:
        print(f"投资组合历史 (股票: {symbol}) 为空 (可能没有交易或数据不足)。跳过分析和绘图。")
        # 仍然可以认为是一次成功的运行，只是没有交易，所以不设error，但指标会反映这一点
        run_result["metrics"] = calculate_performance_metrics(portfolio_history, trades, initial_capital)
        return run_result # 返回空指标

    # 4. 计算并展示绩效指标
    print(f"\n--- 1.4 为 {symbol} 计算绩效指标 ---")
    metrics = calculate_performance_metrics(portfolio_history, trades, initial_capital)
    run_result["metrics"] = metrics

    param_str_for_filename = "_".join([f"{k}{v}" for k,v in strategy_specific_params.items()])
    base_filename_prefix = f"{strategy_id}_{symbol}_{param_str_for_filename}"

    # 生成报告
    report_title_main = f"{strategy_id} on {symbol}"
    report_title_params = f"Params: {strategy_specific_params}, Capital: {initial_capital:.0f}"
    # API端点可能会使用纯英文标题，这里先用中文，后续可调整
    performance_report_text = generate_performance_report(
        metrics, 
        trades, 
        title=f"{report_title_main}\n{report_title_params}",
        commission_rate_pct=commission_rate_pct,
        min_commission=min_commission_per_trade,
        slippage_pct=slippage_pct # 传递给报告生成函数
    )
    print(performance_report_text) # 打印到控制台 (保持中文)
    
    report_filename = f"report_{base_filename_prefix}.txt"
    report_file_path = os.path.join(results_output_dir, report_filename)
    try:
        with open(report_file_path, 'w', encoding='utf-8') as f:
            f.write(performance_report_text)
        print(f"性能报告已保存到: {report_file_path}")
        run_result["report_path"] = report_filename # 返回相对路径
    except IOError as e:
        print(f"保存性能报告到文件失败: {e}")
        run_result["error"] = run_result.get("error", "") + f"; Report save failed: {e}"

    # 5. 绘制并保存投资组合价值图 (使用英文标题)
    print(f"\n--- 1.5 For {symbol}: Plotting Portfolio Value ---")
    plot_title_pv = f"Portfolio Value: {strategy_id} on {symbol} (Params: {strategy_specific_params}) (EN)"
    plot_filename_pv = f"portfolio_{base_filename_prefix}.png"
    plot_output_path_pv_abs = os.path.join(results_output_dir, plot_filename_pv)
    try:
        plot_portfolio_value(portfolio_history, title=plot_title_pv, output_path=plot_output_path_pv_abs)
        run_result["portfolio_value_chart_path"] = plot_filename_pv # 返回相对路径
    except Exception as e_plot_pv:
        print(f"绘制投资组合价值图失败: {e_plot_pv}")
        run_result["error"] = run_result.get("error", "") + f"; Portfolio plot failed: {e_plot_pv}"

    # 6. 绘制并保存单个股票的策略示意图 (使用英文标题)
    print(f"\n--- 1.6 For {symbol}: Plotting Strategy Visualization ---")
    indicator_cols_for_plot = selected_strategy_config.get('indicator_cols', [])
    actual_indicator_cols_present = [col for col in indicator_cols_for_plot if col in data_with_signals.columns]

    if actual_indicator_cols_present:
        strategy_plot_title = f"{strategy_id} Indicators & Signals on {symbol} (Params: {strategy_specific_params}) (EN)"
        strategy_plot_filename = f"strategy_{base_filename_prefix}.png"
        strategy_plot_output_path_abs = os.path.join(results_output_dir, strategy_plot_filename)
        try:
            plot_strategy_on_price(
                data_with_signals, 
                indicator_cols=actual_indicator_cols_present, 
                strategy_name=strategy_id,
                symbol_to_plot=symbol, 
                title=strategy_plot_title,
                output_path=strategy_plot_output_path_abs
            )
            run_result["strategy_chart_path"] = strategy_plot_filename # 返回相对路径
        except Exception as e_plot_strat:
            print(f"绘制策略图失败: {e_plot_strat}")
            run_result["error"] = run_result.get("error", "") + f"; Strategy plot failed: {e_plot_strat}"
    else:
        print(f"策略 {strategy_id} 在 {symbol} 上没有配置指标列或指标列不存在于数据中，跳过策略细节图。")

    print(f"--- 单次回测处理完毕: {strategy_id} for {symbol} with {strategy_specific_params} ---")
    return run_result

def main():
    print("量化交易程序 - 回测流程启动...")

    # 0. 准备主运行的结果子目录 (用于批处理运行)
    main_run_specific_results_dir = os.path.join(RESULTS_DIR, CURRENT_RUN_TAG)
    print(f"\n--- 0. 准备主运行的结果子目录: {main_run_specific_results_dir} ---")
    if not os.path.exists(RESULTS_DIR):
        try: os.makedirs(RESULTS_DIR) 
        except OSError as e: print(f"错误：无法创建顶层结果目录 {RESULTS_DIR}: {e}"); sys.exit(1)
    
    if os.path.exists(main_run_specific_results_dir):
        print(f"清理已存在的子目录: {main_run_specific_results_dir}")
        try: shutil.rmtree(main_run_specific_results_dir)
        except OSError as e: print(f"错误：无法删除子目录 {main_run_specific_results_dir}: {e}"); sys.exit(1)
    try:
        os.makedirs(main_run_specific_results_dir)
        print(f"已创建空的结果子目录: {main_run_specific_results_dir}")
    except OSError as e: print(f"错误：无法创建结果子目录 {main_run_specific_results_dir}: {e}"); sys.exit(1)

    init_db()

    if SELECTED_STRATEGY not in STRATEGY_CONFIG:
        print(f"错误：选择的策略 '{SELECTED_STRATEGY}' 未在 STRATEGY_CONFIG 中定义。可用策略: {list(STRATEGY_CONFIG.keys())}")
        sys.exit(1)
        
    current_strategy_config_details = STRATEGY_CONFIG[SELECTED_STRATEGY]
    
    list_of_strategy_params_to_run = []
    if PERFORM_OPTIMIZATION and 'param_grid' in current_strategy_config_details:
        print("\n--- 准备参数优化 ---")
        param_grid = current_strategy_config_details['param_grid']
        param_names = list(param_grid.keys())
        param_values_list = list(param_grid.values())
        
        for param_combination_values in itertools.product(*param_values_list):
            list_of_strategy_params_to_run.append(dict(zip(param_names, param_combination_values)))
        
        if not list_of_strategy_params_to_run:
            print("警告：参数网格为空，将使用默认参数。")
            default_params = {k: v for k, v in current_strategy_config_details.items() if k not in ['module_name', 'function_name', 'param_grid', 'indicator_cols']}
            list_of_strategy_params_to_run.append(default_params)
        else:
            print(f"将为以下 {len(list_of_strategy_params_to_run)} 组参数运行回测：")
    else:
        print("\n--- 单次回测模式 (使用默认参数) ---")
        default_params = {k: v for k, v in current_strategy_config_details.items() if k not in ['module_name', 'function_name', 'param_grid', 'indicator_cols']}
        list_of_strategy_params_to_run.append(default_params)

    all_runs_summary_metrics_for_main = []
    
    for param_idx, current_strategy_specific_params in enumerate(list_of_strategy_params_to_run):
        if PERFORM_OPTIMIZATION:
            print(f"\n{'='*10} 主流程处理参数组合 {param_idx + 1}/{len(list_of_strategy_params_to_run)}: {current_strategy_specific_params} {'='*10}")
        
        for symbol_to_run in SYMBOLS_TO_BACKTEST: # SYMBOLS_TO_BACKTEST from global scope
            # 调用新的核心执行函数
            single_run_output = execute_single_backtest_run(
                symbol=symbol_to_run,
                strategy_id=SELECTED_STRATEGY,
                strategy_specific_params=current_strategy_specific_params,
                selected_strategy_config=current_strategy_config_details,
                results_output_dir=main_run_specific_results_dir, # main() 使用其自己的结果目录
                start_date=START_DATE, # Global defaults
                end_date=END_DATE,
                initial_capital=INITIAL_CAPITAL,
                commission_rate_pct=COMMISSION_RATE_PCT,
                min_commission_per_trade=MIN_COMMISSION_PER_TRADE,
                slippage_pct=DEFAULT_SLIPPAGE_PCT # 传递滑点参数
            )

            if single_run_output["error"]:
                print(f"处理 {symbol_to_run} 时发生错误: {single_run_output['error']}，跳过此运行的总结。")
                # 可以在这里决定是否要记录这个错误到all_runs_summary_metrics_for_main
                # 例如，添加一个带错误标记的条目
                error_metric_entry = {
                    '股票代码': symbol_to_run,
                    '策略': SELECTED_STRATEGY,
                    '参数': str(current_strategy_specific_params),
                    '错误': single_run_output['error']
                }
                all_runs_summary_metrics_for_main.append(error_metric_entry)
                continue
            
            if single_run_output["metrics"]:
                # 存储当前运行的简要指标 (用于main.py的总结)
                # metrics 已经是字典了，我们只需要添加上下文信息
                metrics_from_run = single_run_output["metrics"]
                summary_entry = {
                    '股票代码': symbol_to_run,
                    '策略': SELECTED_STRATEGY,
                    '参数': str(current_strategy_specific_params), 
                    '总回报率(%)': metrics_from_run.get('总收益率 (%)', float('nan')),
                    '年化回报率(%)': metrics_from_run.get('年化收益率 (%)', float('nan')),
                    '夏普比率': metrics_from_run.get('夏普比率 (年化)', float('nan')), 
                    '最大回撤(%)': metrics_from_run.get('最大回撤 (%)', float('nan')),
                    '总交易次数': metrics_from_run.get('总交易次数', 0),
                    # '买入次数': metrics_from_run.get('买入次数', 0), 
                    # '卖出次数': metrics_from_run.get('卖出次数', 0)
                }
                all_runs_summary_metrics_for_main.append(summary_entry)
            else:
                print(f"警告: {symbol_to_run} 的回测运行没有返回指标数据。")

    # --- 所有参数和股票处理完毕后的总结 (main.py 流程) ---
    if all_runs_summary_metrics_for_main:
        print(f"\n\n{'='*20} Summary of All Batch Backtest Runs (main.py) {'='*20}")
        summary_df = pd.DataFrame(all_runs_summary_metrics_for_main)
        with pd.option_context('display.max_colwidth', None, 'display.width', None, 'display.colheader_justify', 'left'):
            print(summary_df.to_string())

        summary_filename_suffix = "OPTIMIZED" if PERFORM_OPTIMIZATION else "SINGLE_RUN"
        summary_csv_path = os.path.join(main_run_specific_results_dir, f"batch_summary_{SELECTED_STRATEGY}_{summary_filename_suffix}.csv")
        try:
            summary_df.to_csv(summary_csv_path, index=False, encoding='utf-8-sig')
            print(f"\n批处理回测总结已保存到: {summary_csv_path}")
        except IOError as e: print(f"\n保存批处理回测总结到CSV文件失败: {e}")

        if PERFORM_OPTIMIZATION and not summary_df.empty and '夏普比率' in summary_df.columns:
            print(f"\n\n{'='*20} Top Performing Parameter Sets (by Sharpe Ratio) {'='*20}")
            summary_df_copy = summary_df.copy()
            summary_df_copy['夏普比率'] = pd.to_numeric(summary_df_copy['夏普比率'], errors='coerce')
            summary_df_sorted = summary_df_copy.dropna(subset=['夏普比率']).sort_values(by='夏普比率', ascending=False)
            
            if not summary_df_sorted.empty:
                top_n = 5
                print(f"Top {min(top_n, len(summary_df_sorted))} results:")
                with pd.option_context('display.max_colwidth', None, 'display.width', None, 'display.colheader_justify', 'left'):
                    print(summary_df_sorted.head(top_n).to_string())
            else: print("未能找到有效的夏普比率进行排序。")
        elif PERFORM_OPTIMIZATION: print("\n未能执行最佳参数分析 (汇总表为空或缺少夏普比率列)。")

        # --- 参数优化影响图 (main.py 流程) ---
        if PERFORM_OPTIMIZATION and 'param_grid' in current_strategy_config_details and not summary_df.empty:
            param_grid_keys = list(current_strategy_config_details['param_grid'].keys())
            def safe_str_to_dict(s):
                try: return ast.literal_eval(s) if isinstance(s, str) else s if isinstance(s, dict) else {}
                except: return {}

            if '参数' in summary_df.columns:
                summary_df['params_dict'] = summary_df['参数'].apply(safe_str_to_dict)
                # Filter out rows where params_dict might be empty if conversion failed badly
                params_expanded_df = pd.json_normalize(summary_df[summary_df['params_dict'].apply(lambda x: isinstance(x, dict) and bool(x))]['params_dict'])
                
                # Ensure plot_data_df only contains rows that had valid params_dict for merge
                plot_data_df = summary_df[summary_df['params_dict'].apply(lambda x: isinstance(x, dict) and bool(x))].drop(columns=['参数', 'params_dict'])
                
                if not params_expanded_df.empty:
                    params_expanded_df.index = plot_data_df.index # Align indices for merge
                    for p_key in param_grid_keys:
                        if p_key in params_expanded_df.columns:
                            plot_data_df[p_key] = params_expanded_df[p_key]
                        else:
                            plot_data_df[p_key] = pd.NA 
                    
                    metrics_for_impact_charts = ['总回报率', '夏普比率', '最大回撤'] # Removed '胜率' as it's not directly in summary_entry
                                                # Add '总交易次数' if you want to plot its impact
                    
                    for col in metrics_for_impact_charts:
                        if col in plot_data_df.columns:
                            if not pd.api.types.is_numeric_dtype(plot_data_df[col]):
                                plot_data_df[col] = pd.to_numeric(plot_data_df[col], errors='coerce')
                        else:
                            print(f"警告: 指标列 '{col}' 不在 plot_data_df 中，无法为其生成参数影响图。")
                    
                    # Ensure param_grid_keys columns exist in plot_data_df after potential NA introduction
                    valid_param_grid_keys_for_plot = [k for k in param_grid_keys if k in plot_data_df.columns]

                    if not plot_data_df.empty and valid_param_grid_keys_for_plot and not plot_data_df[valid_param_grid_keys_for_plot].isnull().all().all(): 
                        print(f"\n为参数组 {valid_param_grid_keys_for_plot} 生成参数影响图...")
                        for metric_name in metrics_for_impact_charts: 
                            if metric_name not in plot_data_df.columns or plot_data_df[metric_name].isnull().all():
                                print(f"  指标 '{metric_name}' 数据不足，跳过其参数影响图。")
                                continue
                            print(f"  -- 针对指标: {metric_name} --")
                            try:
                                plot_parameter_impact(
                                    results_df=plot_data_df.copy(),
                                    parameters_to_plot=valid_param_grid_keys_for_plot, 
                                    metric_to_plot=metric_name, 
                                    strategy_name=SELECTED_STRATEGY, 
                                    output_dir=main_run_specific_results_dir
                                )
                            except Exception as e_plot:
                                print(f"为指标 '{metric_name}' 生成参数影响图时发生错误: {e_plot}")
                    else:
                        print("警告: 清理后没有足够的数据或有效的参数列来生成参数影响图。")
                else:
                    print("警告: '参数' 列解析后未产生有效的参数字典数据，无法生成参数影响图。")
            else:
                print("警告: '参数' 列不存在于 summary_df 中，无法生成参数影响图。")
        else: 
            if PERFORM_OPTIMIZATION : print("信息：参数优化模式下，跳过参数影响图的生成 (可能因为无有效总结数据或未定义param_grid)。")
    else:
        print("\n没有成功完成的回测运行可供总结。")

    print("\n回测流程结束。")

if __name__ == "__main__":
    main() 
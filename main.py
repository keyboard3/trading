# main.py - 主入口脚本

# 导入必要的模块
from core_engine.data_loader import init_db, load_data_from_db, DB_FILE, OHLCV_TABLE_NAME, import_csv_to_db, DATA_DIR # Added DATA_DIR
from strategies.simple_ma_strategy import dual_moving_average_strategy
from strategies.rsi_strategy import rsi_strategy # <<< 新增导入 RSI 策略
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

# --- 策略配置 --- 
# 用户可以在这里选择要运行的策略和配置其参数
# SELECTED_STRATEGY = 'MA'  # 可选: 'MA' (双均线), 'RSI'
SELECTED_STRATEGY = 'RSI' # <--- 修改这里来选择策略 (或者 'MA')

# --- 参数优化开关 ---
PERFORM_OPTIMIZATION = True # 设置为True以运行参数优化，False则运行单次回测使用下方默认参数

STRATEGY_CONFIG = {
    'MA': {
        'function': dual_moving_average_strategy,
        # MA策略特定参数 (如果MA也需要优化，可仿照RSI添加param_grid)
        'short_window': 20, 
        'long_window': 50,
        'param_grid': { # 示例MA参数网格 (当前未启用优化，但结构备用)
            'short_window': [10, 20],
            'long_window': [30, 50, 60]
        }
    },
    'RSI': {
        'function': rsi_strategy,
        # RSI策略特定参数 (这些作为单次回测或优化未启用时的默认值)
        'period': 14,
        'oversold_threshold': 30,
        'overbought_threshold': 70,
        'param_grid': { # 新增RSI参数网格定义
            'period': [14, 20],
            'oversold_threshold': [25, 30],
            'overbought_threshold': [70, 75]
        }
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

RESULTS_DIR = "results" # 顶层结果目录
CURRENT_RUN_TAG = "RSI_MSFT_ParamOpt_SmallSet" # <<< 新增：当前运行的标签，用于创建子目录

def main():
    print("量化交易程序 - 回测流程启动...")

    # 0. 准备结果子目录
    # 确保顶层 results 目录存在
    if not os.path.exists(RESULTS_DIR):
        try:
            os.makedirs(RESULTS_DIR)
            print(f"已创建顶层结果目录: {RESULTS_DIR}")
        except OSError as e:
            print(f"错误：无法创建顶层结果目录 {RESULTS_DIR}: {e}")
            sys.exit(1)
    
    # 构建并清理当前运行的特定子目录
    run_specific_results_dir = os.path.join(RESULTS_DIR, CURRENT_RUN_TAG)
    print(f"\n--- 0. 准备本次运行的结果子目录: {run_specific_results_dir} ---")
    if os.path.exists(run_specific_results_dir):
        print(f"发现已存在的子目录: {run_specific_results_dir}，将进行清理...")
        try:
            shutil.rmtree(run_specific_results_dir)
            print(f"成功删除子目录: {run_specific_results_dir}")
        except OSError as e:
            print(f"错误：无法删除子目录 {run_specific_results_dir}: {e}")
            sys.exit(1) # 如果无法清理，则退出以避免结果混乱
    
    try:
        os.makedirs(run_specific_results_dir)
        print(f"已创建空的结果子目录: {run_specific_results_dir}")
    except OSError as e:
        print(f"错误：无法创建结果子目录 {run_specific_results_dir}: {e}")
        sys.exit(1) # 如果无法创建目录，也退出

    # 0. 初始化数据库 (确保数据库和表存在)
    print("\n--- 0. 初始化数据库 ---")
    init_db()

    # 0.1 确保results目录存在
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)
        print(f"已创建目录: {RESULTS_DIR}")

    # 检查选择的策略是否配置正确
    if SELECTED_STRATEGY not in STRATEGY_CONFIG:
        print(f"错误：选择的策略 '{SELECTED_STRATEGY}' 未在 STRATEGY_CONFIG 中定义。")
        print(f"可用策略: {list(STRATEGY_CONFIG.keys())}")
        sys.exit(1)
        
    current_strategy_details = STRATEGY_CONFIG[SELECTED_STRATEGY]
    strategy_function = current_strategy_details['function']
    
    # --- 根据 PERFORM_OPTIMIZATION 决定参数列表 ---
    list_of_strategy_params_to_run = []
    if PERFORM_OPTIMIZATION and 'param_grid' in current_strategy_details:
        print("\n--- 准备参数优化 ---")
        param_grid = current_strategy_details['param_grid']
        param_names = list(param_grid.keys())
        param_values_list = list(param_grid.values())
        
        for param_combination_values in itertools.product(*param_values_list):
            list_of_strategy_params_to_run.append(dict(zip(param_names, param_combination_values)))
        
        if not list_of_strategy_params_to_run:
            print("警告：参数网格为空或配置不正确，将使用默认参数进行单次回测。")
            # 回退到使用默认参数
            default_params = {k: v for k, v in current_strategy_details.items() if k not in ['function', 'param_grid']}
            list_of_strategy_params_to_run.append(default_params)
        else:
            print(f"将为以下 {len(list_of_strategy_params_to_run)} 组参数运行回测：")
            # for p_idx, p_set in enumerate(list_of_strategy_params_to_run):
            #     print(f"  参数组 {p_idx+1}: {p_set}")
    else:
        print("\n--- 单次回测模式 (使用默认参数) ---")
        default_params = {k: v for k, v in current_strategy_details.items() if k not in ['function', 'param_grid']}
        list_of_strategy_params_to_run.append(default_params)

    all_runs_summary_metrics = [] # 用于存储所有回测运行的性能总结
    
    # --- 外层循环：遍历参数组合 ---
    for param_idx, strategy_params in enumerate(list_of_strategy_params_to_run):
        if PERFORM_OPTIMIZATION:
            print(f"\n{'='*10} 开始处理参数组合 {param_idx + 1}/{len(list_of_strategy_params_to_run)}: {strategy_params} {'='*10}")
        
        # 原始的 strategy_params 获取逻辑不再需要，因为已经在这里循环了

        print(f"\n--- 1. 回测配置 ---CNY")
        print(f"选定策略: {SELECTED_STRATEGY}")
        print(f"策略参数: {strategy_params}")
        print(f"初始资金: {INITIAL_CAPITAL}")
        print(f"回测股票代码: {SYMBOLS_TO_BACKTEST}")
        print(f"数据时间范围: 从 {START_DATE or '最早'} 到 {END_DATE or '最新'}")

        # --- 内层循环：循环处理每个选定的股票代码 (保持不变) ---
        for symbol in SYMBOLS_TO_BACKTEST:
            print(f"\n\n{'='*20} 正在处理股票: {symbol} (参数: {strategy_params}) {'='*20}")
            
            # 2. 从数据库加载特定股票的数据
            print(f"\n--- 2.1 为 {symbol} 加载数据 ---")
            # load_data_from_db 应该返回特定symbol的数据，且日期已排序
            market_data_for_symbol = load_data_from_db(symbols=[symbol], start_date=START_DATE, end_date=END_DATE)
            
            if market_data_for_symbol is None or market_data_for_symbol.empty:
                print(f"数据库中未找到股票 {symbol} 的数据 (表: {OHLCV_TABLE_NAME} 在 {DB_FILE}).")
                if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) < 100: # 简单检查文件是否几乎为空
                    print(f"数据库 {DB_FILE} 可能为空或不存在。")
                sample_csv_path_for_prompt = os.path.join(DATA_DIR, 'sample_stock_data.csv')
                print("如果您是首次运行或数据库为空，请考虑：")
                print(f" - 运行 `python -m core_engine.data_fetcher` 来从yfinance下载数据 (例如MSFT, AAPL)。")
                print(f" - 或运行 `python -m core_engine.data_loader` 来从 {sample_csv_path_for_prompt} 导入示例数据。")
                print(f"跳过股票 {symbol} 的回测。")
                continue # 跳到下一个股票
                
            print(f"成功为 {symbol} 从数据库加载 {len(market_data_for_symbol)} 条数据。")
            print(f"数据期间: {market_data_for_symbol.index.min()} to {market_data_for_symbol.index.max()}")

            # 3. 为当前股票数据生成交易信号
            print(f"\n--- 2.2 为 {symbol} 生成交易信号 ({SELECTED_STRATEGY}策略) ---")
            # 策略函数现在接收单个股票的DataFrame
            data_with_signals = strategy_function(
                market_data_for_symbol.copy(), # 传入副本以避免修改原始加载的数据
                **strategy_params
            )
            if data_with_signals is None or data_with_signals.empty or 'signal' not in data_with_signals.columns:
                print(f"为 {symbol} 生成信号失败或结果为空/不含signal列，回测终止。")
                continue
            print(f"股票 {symbol} 的交易信号已生成。")
            # print(f"带信号的数据预览 (股票: {symbol}, 取信号不为0的行):\n", data_with_signals[data_with_signals['signal'] != 0].head())

            # 4. 执行回测
            print(f"\n--- 2.3 为 {symbol} 执行回测 ---CNY")
            # 注意：run_backtest 当前实现是针对单个股票 DataFrame 的，所以这里的循环是合适的
            portfolio_history, trades = run_backtest(
                data_with_signals, # data_with_signals 现在是单股票含信号的数据
                INITIAL_CAPITAL,
                commission_rate_pct=COMMISSION_RATE_PCT, # <<< 传递手续费率
                min_commission=MIN_COMMISSION_PER_TRADE  # <<< 传递最低手续费
            )
            if portfolio_history is None: 
                print(f"为 {symbol} 执行回测失败，分析终止。")
                continue
            print(f"股票 {symbol} 的回测执行完毕。")
            if portfolio_history.empty:
                print(f"投资组合历史 (股票: {symbol}) 为空 (可能没有交易或数据不足)。")
            # else:
                # print(f"投资组合历史 (股票: {symbol}, 后5条):\n", portfolio_history.tail())

            # 5. 计算并展示绩效指标
            print(f"\n--- 2.4 为 {symbol} 计算并展示绩效指标 ---CNY")
            if not portfolio_history.empty:
                # calculate_performance_metrics 也应针对单次（单一股票）回测的结果
                metrics = calculate_performance_metrics(portfolio_history, trades, INITIAL_CAPITAL)
                report_title = f"{SELECTED_STRATEGY} 策略在 {symbol}上的回测报告\\n参数: {strategy_params}\\n初始资金: {INITIAL_CAPITAL}" # strategy_params 已是当前循环的
                performance_report_text = generate_performance_report(
                    metrics, 
                    trades, 
                    title=report_title,
                    commission_rate_pct=COMMISSION_RATE_PCT, # <<< 传递手续费率
                    min_commission=MIN_COMMISSION_PER_TRADE    # <<< 传递最低手续费
                )
                print(performance_report_text) # 打印到控制台

                # 文件名中也应包含参数信息以避免覆盖，这会产生很多文件，后续可以考虑如何管理
                # 为了简化，暂时保持文件名只包含策略和股票，但报告内容会包含参数
                param_str_for_filename = "_".join([f"{k}{v}" for k,v in strategy_params.items()])
                report_filename = f"report_{SELECTED_STRATEGY}_{symbol}_{param_str_for_filename}.txt"
                report_file_path = os.path.join(run_specific_results_dir, report_filename)
                try:
                    with open(report_file_path, 'w', encoding='utf-8') as f:
                        f.write(performance_report_text)
                    print(f"\n性能报告已保存到: {report_file_path}")
                except IOError as e:
                    print(f"\n保存性能报告到文件失败: {e}")
                
                # 存储当前运行的简要指标
                current_run_metrics = {
                    '股票代码': symbol,
                    '策略': SELECTED_STRATEGY,
                    '参数': str(strategy_params), # 转为字符串以便DataFrame显示
                    '总回报率(%)': metrics.get('总收益率 (%)', float('nan')),
                    '年化回报率(%)': metrics.get('年化收益率 (%)', float('nan')),
                    '夏普比率': metrics.get('夏普比率 (年化)', float('nan')), # 确保这里的键名与 performance_analyzer.py 中的完全一致
                    '最大回撤(%)': metrics.get('最大回撤 (%)', float('nan')),
                    '买入次数': metrics.get('买入次数', 0), # 修改为买入次数
                    '卖出次数': metrics.get('卖出次数', 0)  # 修改为卖出次数
                }
                all_runs_summary_metrics.append(current_run_metrics)

                # 6. 绘制并保存投资组合价值图
                print(f"\n--- 2.5 For {symbol}: Plotting Portfolio Value ---")
                # title_pv 现在使用英文，并由具体参数构成
                plot_title_pv = f"Portfolio Value: {SELECTED_STRATEGY} on {symbol} (Params: {strategy_params})"
                plot_filename_pv = f"portfolio_{SELECTED_STRATEGY}_{symbol}_{param_str_for_filename}.png"
                plot_output_path_pv = os.path.join(run_specific_results_dir, plot_filename_pv)
                plot_portfolio_value(portfolio_history, title=plot_title_pv, output_path=plot_output_path_pv)

                # 7. 绘制并保存单个股票的策略示意图
                print(f"\n--- 2.6 For {symbol}: Plotting Strategy Visualization ---")
                indicator_cols_map = {
                    'MA': ['short_ma', 'long_ma'],
                    'RSI': ['rsi']
                }
                indicator_cols_for_plot = indicator_cols_map.get(SELECTED_STRATEGY, [])
                
                actual_indicator_cols_present = [col for col in indicator_cols_for_plot if col in data_with_signals.columns]
                
                if not actual_indicator_cols_present and indicator_cols_for_plot:
                     print(f"Warning: Expected indicator columns {indicator_cols_for_plot} for strategy {SELECTED_STRATEGY} not found in data for {symbol}. Cannot plot strategy details.")
                elif actual_indicator_cols_present:
                    # strategy_plot_title 现在使用英文
                    strategy_plot_title = f"{SELECTED_STRATEGY} Strategy Indicators & Signals on {symbol}\nParams: {strategy_params}"
                    strategy_plot_filename = f"strategy_{SELECTED_STRATEGY}_{symbol}_{param_str_for_filename}.png"
                    strategy_plot_output_path = os.path.join(run_specific_results_dir, strategy_plot_filename)
                    
                    plot_strategy_on_price(
                        data_with_signals, 
                        indicator_cols=actual_indicator_cols_present, 
                        strategy_name=SELECTED_STRATEGY,
                        symbol_to_plot=symbol, 
                        title=strategy_plot_title,
                        output_path=strategy_plot_output_path
                    )
                else:
                    print(f"Strategy {SELECTED_STRATEGY} has no specific indicator columns configured for plotting on {symbol}.")

            else:
                print(f"Portfolio history for {symbol} is empty. Skipping metrics and plots.")
            
            print(f"--- Processing for {symbol} finished ---")

        # --- 所有股票处理完毕后的总结 ---
        if all_runs_summary_metrics:
            print(f"\n\n{'='*20} Summary of All Backtest Runs {'='*20}")
            summary_df = pd.DataFrame(all_runs_summary_metrics)
            # 为了更好的对齐长参数列，调整pandas显示选项
            # 使用 option_context 确保这些设置只在此处生效
            with pd.option_context('display.max_colwidth', None, # 不截断列内容
                                   'display.width', None,      # 尽可能使用终端可用宽度
                                   'display.colheader_justify', 'left'): # 列标题左对齐
                print(summary_df.to_string()) # 默认会打印索引，与您提供的输出一致

            summary_filename_suffix = "OPTIMIZED" if PERFORM_OPTIMIZATION else "SINGLE_RUN"
            summary_csv_path = os.path.join(run_specific_results_dir, f"all_backtests_summary_{SELECTED_STRATEGY}_{summary_filename_suffix}.csv")
            try:
                summary_df.to_csv(summary_csv_path, index=False, encoding='utf-8-sig') # utf-8-sig for Excel compatibility
                print(f"\n所有回测总结已保存到: {summary_csv_path}")
            except IOError as e:
                print(f"\n保存所有回测总结到CSV文件失败: {e}")

            # --- 找出并打印最佳参数组合 (基于夏普比率) ---
            if PERFORM_OPTIMIZATION and not summary_df.empty and '夏普比率' in summary_df.columns:
                print(f"\n\n{'='*20} Top Performing Parameter Sets (by Sharpe Ratio) {'='*20}")
                # 转换夏普比率为数值类型，非数值转为NaN，以便正确排序
                summary_df_copy = summary_df.copy() # 操作副本以避免修改原始DataFrame
                summary_df_copy['夏普比率'] = pd.to_numeric(summary_df_copy['夏普比率'], errors='coerce')
                # 移除夏普比率为NaN的行，这些通常是没有交易或数据不足的情况
                summary_df_sorted = summary_df_copy.dropna(subset=['夏普比率']).sort_values(by='夏普比率', ascending=False)
                
                if not summary_df_sorted.empty:
                    # 打印排名前N个的结果，例如前5个
                    top_n = 5
                    print(f"Top {min(top_n, len(summary_df_sorted))} results:")
                    # 使用 option_context 确保这些设置只在此处生效，同上
                    with pd.option_context('display.max_colwidth', None, 
                                           'display.width', None, 
                                           'display.colheader_justify', 'left'):
                        print(summary_df_sorted.head(top_n).to_string())
                else:
                    print("未能找到有效的夏普比率进行排序 (可能所有回测都没有产生有效夏普比率)。")
            elif PERFORM_OPTIMIZATION:
                print("\n未能执行最佳参数分析 (汇总表为空或缺少夏普比率列)。")

            # --- (新增) 绘制参数影响图 --- (仅在优化模式且有数据时)
            if PERFORM_OPTIMIZATION and not summary_df.empty:
                print(f"\n\n{'='*20} Generating Parameter Impact Plots {'='*20}")
                # 假设RSI策略的参数是 ['period', 'oversold_threshold', 'overbought_threshold']
                # 我们主要关注 'period' 对 '夏普比率' 和 '总回报率(%)' 的影响
                # 其他参数 ('oversold_threshold', 'overbought_threshold') 的影响会通过平均来体现
                
                # 获取当前策略的参数名 (不包括 'function' 和 'param_grid')
                potential_params_to_plot = list(STRATEGY_CONFIG[SELECTED_STRATEGY]['param_grid'].keys())

                for symbol_to_analyze in SYMBOLS_TO_BACKTEST:
                    print(f"-- Plotting for symbol: {symbol_to_analyze} --")
                    for param_name in potential_params_to_plot: # 对每个可优化的参数都尝试绘图
                        # 绘制对夏普比率的影响
                        plot_parameter_impact(
                            summary_df=summary_df,
                            target_symbol=symbol_to_analyze,
                            parameter_to_plot=param_name,
                            metric_to_plot='夏普比率',
                            output_dir=run_specific_results_dir
                        )
                        # 绘制对总回报率的影响
                        plot_parameter_impact(
                            summary_df=summary_df,
                            target_symbol=symbol_to_analyze,
                            parameter_to_plot=param_name,
                            metric_to_plot='总回报率(%)',
                            output_dir=run_specific_results_dir
                        )
                        # 如果需要，可以绘制对其他指标的影响，或测试 other_params_to_fix 功能
                        # 例如，固定 oversold_threshold=30 来观察 period 对 夏普比率的影响
                        # fixed_other_params_example = {'oversold_threshold': 30} # 这需要根据实际参数名调整
                        # plot_parameter_impact(
                        #     summary_df=summary_df,
                        #     target_symbol=symbol_to_analyze,
                        #     parameter_to_plot='period', # 假设我们观察 period
                        #     metric_to_plot='夏普比率',
                        #     output_dir=RESULTS_DIR,
                        #     other_params_to_fix=fixed_other_params_example 
                        # )
        else:
            print("\n没有成功完成的回测运行可供总结。")

    print("\n回测流程结束。")

if __name__ == "__main__":
    main() 
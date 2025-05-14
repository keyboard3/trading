import yfinance as yf
import pandas as pd
import os
# import sqlite3 # Though not directly used, good to be aware if extending # No longer needed here directly
from datetime import datetime, timedelta

# 假设 data_loader.py 与此文件在同一目录 (core_engine)
from .data_loader import save_df_to_db, init_db, DB_FILE, delete_data_from_db, OHLCV_MINUTE_TABLE_NAME, OHLCV_DAILY_TABLE_NAME

def fetch_and_save_ohlcv(symbols: list, start_date: str, end_date: str, 
                         interval: str, target_table_name: str, 
                         db_path=DB_FILE):
    """
    从 Yahoo Finance 下载指定股票列表的OHLCV数据，
    删除数据库中对应范围的旧数据，然后保存新数据到SQLite数据库的指定表中。
    interval: yfinance支持的间隔字符串, e.g., "1m", "5m", "1d".
    target_table_name: 要保存到的数据库表名。
    """
    if not isinstance(symbols, list):
        symbols = [symbols]

    print(f"\n开始从Yahoo Finance获取 {', '.join(symbols)} 的数据 (频率: {interval})，"
          f"时间范围: {start_date} 到 {end_date}，保存到表: {target_table_name}...")

    try:
        # 使用传入的 interval 参数
        data_multi = yf.download(symbols, start=start_date, end=end_date, 
                                 interval=interval, progress=False)

        if data_multi.empty:
            print(f"未能下载到任何数据 (频率: {interval})，可能股票代码无效或指定日期范围无数据。")
            return

        print(f"已成功从 yfinance 下载原始数据 (频率: {interval})，共 {len(data_multi)} 条记录 (可能包含多个股票的合并数据)。")
        
        ohlcv_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        all_processed_data = []

        if not isinstance(data_multi.columns, pd.MultiIndex):
            # 处理单股票下载或yf返回非MultiIndex的情况
            if len(symbols) == 1:
                # 检查是否有实际数据列，而不仅仅是空的DataFrame结构
                if not all(col in data_multi.columns for col in ohlcv_columns):
                    print(f"警告: 单股票 {symbols[0]} (频率: {interval}) 下载的数据不包含所有OHLCV列。可用列: {data_multi.columns.tolist()}")
                    if data_multi.empty or data_multi.shape[0] == 0:
                        print(f"单股票 {symbols[0]} (频率: {interval}) 下载的数据为空。跳过。")
                        return # 或者 continue 如果在循环中
                    # 尝试只选择存在的OHLCV列
                    existing_ohlcv_cols = [col for col in ohlcv_columns if col in data_multi.columns]
                    if not existing_ohlcv_cols:
                        print(f"单股票 {symbols[0]} (频率: {interval}) 下载的数据中无任何OHLCV列。跳过。")
                        return
                    df_flat = data_multi[existing_ohlcv_cols].copy()
                else:
                    df_flat = data_multi[ohlcv_columns].copy()
                
                df_flat.rename(columns={
                    'Open': 'open', 'High': 'high', 'Low': 'low',
                    'Close': 'close', 'Volume': 'volume'
                }, inplace=True)
                df_flat['symbol'] = symbols[0]
                if not isinstance(df_flat.index, pd.DatetimeIndex):
                    df_flat.index = pd.to_datetime(df_flat.index)
                # 对于分钟数据，yf返回的索引名可能是 Datetime，对于日线是 Date
                df_flat.index.name = 'timestamp_col' # 临时名称，后续统一为 'timestamp'
                all_processed_data = [df_flat.reset_index().rename(columns={'timestamp_col': 'timestamp'})]
            else:
                print(f"警告: 下载了多个股票 (频率: {interval})，但yfinance返回的列不是预期的MultiIndex。请检查数据格式。")
                return 
        else: 
            # 处理多股票下载 (MultiIndex columns)
            valid_ohlcv_columns_in_source = [col for col in ohlcv_columns if col in data_multi.columns.levels[0]]
            if not valid_ohlcv_columns_in_source:
                print(f"错误: yfinance 返回的数据中 (频率: {interval})，MultiIndex 列的第一层不包含任何预期的 OHLCV 列: {ohlcv_columns}")
                print(f"实际第一层列名: {data_multi.columns.levels[0]}")
                return
            
            data_selected = data_multi[valid_ohlcv_columns_in_source]
            df_stacked = data_selected.stack(level=1, future_stack=True).reset_index() # stack Ticker
            
            rename_dict = {
                data_multi.index.name if data_multi.index.name else 'Date': 'timestamp', # yf索引名可能是 Date 或 Datetime
                'level_1': 'symbol', # yf <0.2.38 可能是 Ticker, >=0.2.38 可能是 level_1 (取决于stack)
                                    # 我们需要更可靠的方式获取股票代码列名
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            }
            # 尝试找到 stack 后的股票代码列名
            # yfinance 0.2.38 changed stacked column name from 'Ticker' to 'level_1'
            # We need to handle this robustly.
            if 'Ticker' in df_stacked.columns: # Older yfinance
                rename_dict['Ticker'] = 'symbol'
            elif 'level_1' in df_stacked.columns: # Newer yfinance default for stack(level=1)
                rename_dict['level_1'] = 'symbol'
            else:
                 # Fallback: if yf.download was for single symbol but still gave multiindex (e.g. with 'Adj Close')
                 # and we stacked it, the symbol might not be a column. This shouldn't happen with our ohlcv_columns selection.
                 # However, if yf.download(symbols=["X"], ...) and X is a single stock, it might result in a non-multiindex path first.
                 # This path (MultiIndex) is for len(symbols) > 1 or when yf decides to return MultiIndex anyway.
                 print(f"警告: 无法在stack后的DataFrame中找到股票代码列 ('Ticker' or 'level_1'). 列: {df_stacked.columns.tolist()}")
                 # If only one symbol was requested and we are in this multi-index path for some reason, assume it.
                 if len(symbols) == 1:
                     df_stacked['symbol'] = symbols[0]
                     print(f"假设股票代码为: {symbols[0]}")
                 else:
                     print("无法确定股票代码，跳过此数据集。")
                     return

            df_stacked.rename(columns=rename_dict, inplace=True)
            final_cols_order = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
            existing_final_cols = [col for col in final_cols_order if col in df_stacked.columns]
            df_final_for_db = df_stacked[existing_final_cols]
            all_processed_data = [df_final_for_db]

        if not all_processed_data:
            print(f"没有成功处理任何数据 (频率: {interval})。")
            return

        combined_df = pd.concat(all_processed_data)
        
        if combined_df.empty:
            print(f"所有下载并处理的数据 (频率: {interval}) 合并后为空，不执行数据库保存。")
            return
        
        if 'timestamp' not in combined_df.columns:
            print(f"错误：处理后的数据中缺少 'timestamp' 列 (频率: {interval})。列: {combined_df.columns.tolist()}")
            return
        
        combined_df['timestamp'] = pd.to_datetime(combined_df['timestamp']) # 确保是datetime
        # 移除任何完全是 NaT 的行 (通常是因为yf在某些股票的特定日期没有数据)
        combined_df.dropna(subset=['timestamp'], inplace=True)
        # 移除OHLC都为NaN的行 (这些通常是由于股票在某些日期未交易，但yf填充了索引)
        combined_df.dropna(subset=['open', 'high', 'low', 'close'], how='all', inplace=True)
        
        if combined_df.empty:
            print(f"数据在清理NaT和NaN值后为空 (频率: {interval})。不执行数据库保存。")
            return

        print(f"准备从数据库表 '{target_table_name}' 中删除 {symbols} 在 {start_date} 到 {end_date} 范围内的旧数据 (频率: {interval})...")
        delete_data_from_db(symbols=symbols, start_date=start_date, end_date=end_date, 
                            table_name=target_table_name, # 使用传入的 target_table_name
                            db_path=db_path)

        print(f"准备将总共 {len(combined_df)} 条数据 (频率: {interval}) 保存到数据库表 '{target_table_name}'...")
        save_df_to_db(combined_df, target_table_name, db_path) # 使用传入的 target_table_name

    except Exception as e:
        print(f"在 fetch_and_save_ohlcv (频率: {interval}, 表: {target_table_name}) 中发生错误: {e}")
        import traceback
        print(traceback.format_exc())

    print(f"数据获取和保存流程结束 (频率: {interval}, 表: {target_table_name})。")


if __name__ == '__main__':
    print("--- data_fetcher.py 模块测试 ---")
    
    print("确保数据库和表已初始化...")
    init_db() # 这会创建 ohlcv_daily_data 和 ohlcv_1m_data 表

    test_symbols = ['MSFT', 'AAPL'] 
    
    # --- 获取和保存1分钟数据 (最近7天) ---
    minute_end_date_str = datetime.now().strftime('%Y-%m-%d')
    # yfinance 对1分钟数据的回溯通常限制在7天内 (对于某些API可能是30天，但7天更保险)
    # 我们取最近5天的数据以确保能拿到
    minute_start_date_str = (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d') # 获取包括今天在内的最近7天的数据点
    print(f"\n准备获取1分钟数据: 股票={test_symbols}, 开始日期={minute_start_date_str}, 结束日期={minute_end_date_str}")
    fetch_and_save_ohlcv(symbols=test_symbols, 
                         start_date=minute_start_date_str, 
                         end_date=minute_end_date_str,
                         interval="1m",
                         target_table_name=OHLCV_MINUTE_TABLE_NAME)

    # --- 获取和保存日线数据 (最近一年) ---
    daily_end_date_str = datetime.now().strftime('%Y-%m-%d')
    daily_start_date_str = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    print(f"\n准备获取日线数据: 股票={test_symbols}, 开始日期={daily_start_date_str}, 结束日期={daily_end_date_str}")
    fetch_and_save_ohlcv(symbols=test_symbols, 
                         start_date=daily_start_date_str, 
                         end_date=daily_end_date_str,
                         interval="1d",
                         target_table_name=OHLCV_DAILY_TABLE_NAME)

    print("\n--- data_fetcher.py 模块测试结束 ---")
    print(f"请检查数据库文件 {DB_FILE} 中的表 {OHLCV_MINUTE_TABLE_NAME} 和 {OHLCV_DAILY_TABLE_NAME} 是否有新数据或已更新。")
    print(f"你可以使用 core_engine.data_loader.py 中的 query_data_from_db 函数来查询数据库进行验证。例如:")
    print(f"  from core_engine.data_loader import query_data_from_db, OHLCV_MINUTE_TABLE_NAME, OHLCV_DAILY_TABLE_NAME")
    print(f"  df_1m = query_data_from_db(symbols=['MSFT'], table_name=OHLCV_MINUTE_TABLE_NAME)")
    print(f"  print(df_1m.head())")
    print(f"  df_1d = query_data_from_db(symbols=['MSFT'], table_name=OHLCV_DAILY_TABLE_NAME)")
    print(f"  print(df_1d.head())") 
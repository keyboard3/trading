import yfinance as yf
import pandas as pd
import os
import sqlite3 # Though not directly used, good to be aware if extending
from datetime import datetime, timedelta

# 假设 data_loader.py 与此文件在同一目录 (core_engine)
from .data_loader import save_df_to_db, init_db, DB_FILE, OHLCV_TABLE_NAME, delete_data_from_db

def fetch_and_save_ohlcv(symbols: list, start_date: str, end_date: str,
                         db_path=DB_FILE, table_name=OHLCV_TABLE_NAME):
    """
    从 Yahoo Finance 下载指定股票列表的OHLCV数据，
    删除数据库中对应范围的旧数据，然后保存新数据到SQLite数据库。
    """
    if not isinstance(symbols, list):
        symbols = [symbols] 

    print(f"开始从Yahoo Finance获取 {', '.join(symbols)} 的数据，时间范围: {start_date} 到 {end_date}...")

    try:
        data_multi = yf.download(symbols, start=start_date, end=end_date, progress=False)

        if data_multi.empty:
            print(f"未能下载到任何数据，可能股票代码无效或指定日期范围无数据。")
            return

        print(f"已成功从 yfinance 下载原始数据，共 {len(data_multi)} 条记录 (可能包含多个股票的合并数据)。")
        
        ohlcv_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        all_processed_data = []

        if not isinstance(data_multi.columns, pd.MultiIndex):
            if len(symbols) == 1:
                df_flat = data_multi[ohlcv_columns].copy()
                df_flat.rename(columns={
                    'Open': 'open', 'High': 'high', 'Low': 'low',
                    'Close': 'close', 'Volume': 'volume'
                }, inplace=True)
                df_flat['symbol'] = symbols[0]
                # 对于单股票下载，确保索引是日期时间格式，并将其命名为 'Date' 以便后续处理
                if not isinstance(df_flat.index, pd.DatetimeIndex):
                    df_flat.index = pd.to_datetime(df_flat.index)
                df_flat.index.name = 'Date' # 确保索引名为'Date'，与多股票情况一致
                all_processed_data = [df_flat.reset_index()] # 重置索引，使Date成为一列
            else:
                print("警告: 下载了多个股票，但yfinance返回的列不是预期的MultiIndex。请检查数据格式。")
                # 此处可能需要更复杂的处理逻辑，或者假设数据已经扁平化且包含symbol列
                return 
        else: 
            valid_ohlcv_columns = [col for col in ohlcv_columns if col in data_multi.columns.levels[0]]
            if not valid_ohlcv_columns:
                print(f"错误: yfinance 返回的数据中，MultiIndex 列的第一层不包含任何预期的 OHLCV 列: {ohlcv_columns}")
                print(f"实际第一层列名: {data_multi.columns.levels[0]}")
                return
            data_selected = data_multi[valid_ohlcv_columns]
            df_stacked = data_selected.stack(level=1, future_stack=True).reset_index()
            rename_dict = {
                'Date': 'timestamp', 
                'Ticker': 'symbol',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            }
            df_stacked.rename(columns=rename_dict, inplace=True)
            final_cols_order = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
            existing_final_cols = [col for col in final_cols_order if col in df_stacked.columns]
            df_final_for_db = df_stacked[existing_final_cols]
            all_processed_data = [df_final_for_db]

        if not all_processed_data:
            print("没有成功处理任何数据。")
            return

        combined_df = pd.concat(all_processed_data)
        
        if combined_df.empty:
            print("所有下载并处理的数据合并后为空，不执行数据库保存。")
            return
        
        # 在保存新数据之前，删除数据库中对应范围的旧数据
        print(f"\n准备从数据库中删除 {symbols} 在 {start_date} 到 {end_date} 范围内的旧数据...")
        delete_data_from_db(symbols=symbols, start_date=start_date, end_date=end_date, 
                            db_path=db_path, table_name=table_name)

        print(f"\n准备将总共 {len(combined_df)} 条数据保存到数据库...")
        # combined_df 中的 'timestamp' 列应该是datetime对象或可以转换为datetime的字符串
        # save_df_to_db 会处理 reset_index (如果索引是'Date') 和列名小写
        # 这里需要确保 combined_df 的 'timestamp' 列是pd.to_datetime转换过的，并且索引是标准的RangeIndex
        if 'timestamp' in combined_df.columns:
            combined_df['timestamp'] = pd.to_datetime(combined_df['timestamp'])
        else:
            print("错误：处理后的数据中缺少 'timestamp' 列。")
            return
            
        # save_df_to_db 期望日期作为索引名为 'Date' 或已有名为 'timestamp' 的列
        # 如果 'timestamp' 已经是列，且索引是RangeIndex，则 save_df_to_db 可以直接处理
        # 如果 combined_df 的索引是日期时间，需要先 reset_index()，然后确保日期列名为 'timestamp'
        # 我们的 df_final_for_db 和单股票的 df_flat.reset_index() 已经使日期成为 'timestamp' 列

        save_df_to_db(combined_df, table_name, db_path) 

    except Exception as e:
        print(f"在 fetch_and_save_ohlcv 中发生错误: {e}")
        import traceback
        print(traceback.format_exc())

    print(f"数据获取和保存流程结束。")


if __name__ == '__main__':
    print("--- data_fetcher.py 模块测试 ---")
    
    print("确保数据库和表已初始化...")
    init_db()

    test_symbols = ['MSFT', 'AAPL'] 
    end_date_str = datetime.now().strftime('%Y-%m-%d')
    # start_date_str = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d') # 原来是30天
    start_date_str = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d') # 改为获取一年数据

    print(f"测试参数: 股票={test_symbols}, 开始日期={start_date_str}, 结束日期={end_date_str}")

    fetch_and_save_ohlcv(test_symbols, start_date_str, end_date_str)

    print("\n--- data_fetcher.py 模块测试结束 ---")
    print(f"请检查数据库文件 {DB_FILE} 中的表 {OHLCV_TABLE_NAME} 是否有新数据或已更新。")
    print("你也可以使用 core_engine.data_loader.py 中的测试部分来查询数据库。") 
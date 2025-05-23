import pandas as pd
import sqlite3
import os
from datetime import datetime
from typing import Optional
import yfinance as yf # Import yfinance
import argparse # Import argparse

# --- 数据库配置 ---
DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "market_data.db")
OHLCV_DAILY_TABLE_NAME = "ohlcv_daily_data"  # 存储日线或更长周期数据
OHLCV_MINUTE_TABLE_NAME = "ohlcv_1m_data"    # 存储1分钟K线数据
# OHLCV_TABLE_NAME = "ohlcv_data" # 旧的表名，将被替换
# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

def _check_and_create_table(conn, table_name, sql_create_table_query):
    """检查表是否存在，如果不存在则创建。"""
    try:
        cursor = conn.cursor()
        # 检查表是否存在
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        if cursor.fetchone() is None:
            # 表不存在，创建表
            cursor.execute(sql_create_table_query)
            conn.commit()
            print(f"表 '{table_name}' 已成功创建。")
        # else:
            # print(f"表 '{table_name}' 已存在。")
    except sqlite3.Error as e:
        print(f"检查或创建表 '{table_name}' 时发生错误: {e}")
        # Consider re-raising or handling more gracefully depending on requirements
        raise

def init_db(db_path=DB_FILE):
    """初始化数据库和表结构。"""
    print(f"初始化数据库于: {db_path}")
    os.makedirs(os.path.dirname(db_path), exist_ok=True) # 确保数据库文件所在的目录存在
    
    # SQL语句 - 创建日线数据表 (或者可以存储其他较长周期数据)
    sql_create_daily_table = f"""
    CREATE TABLE IF NOT EXISTS {OHLCV_DAILY_TABLE_NAME} (
        timestamp DATETIME NOT NULL,
        symbol TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume INTEGER,
        PRIMARY KEY (timestamp, symbol)
    );
    """

    # SQL语句 - 创建1分钟K线数据表
    sql_create_minute_table = f"""
    CREATE TABLE IF NOT EXISTS {OHLCV_MINUTE_TABLE_NAME} (
        timestamp DATETIME NOT NULL,
        symbol TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume INTEGER,
        PRIMARY KEY (timestamp, symbol)
    );
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        print("数据库连接成功。")
        _check_and_create_table(conn, OHLCV_DAILY_TABLE_NAME, sql_create_daily_table)
        _check_and_create_table(conn, OHLCV_MINUTE_TABLE_NAME, sql_create_minute_table)
        
    except sqlite3.Error as e:
        print(f"数据库初始化错误: {e}")
    finally:
        if conn:
            conn.close()

def save_df_to_db(df: pd.DataFrame, table_name: str, db_path=DB_FILE, if_exists='append'):
    """
    将 Pandas DataFrame 保存到 SQLite 数据库的指定表中。
    DataFrame 应该包含 'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume' 列。
    'timestamp' 列应该是 datetime 对象。
    """
    if df.empty:
        print(f"数据为空，不执行保存到表 '{table_name}' 的操作。")
        return

    required_cols = {'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume'}
    if not required_cols.issubset(df.columns):
        missing_cols = required_cols - set(df.columns)
        print(f"错误: DataFrame 中缺少必要的列: {missing_cols}。无法保存到表 '{table_name}'。")
        return

    # 确保 'timestamp' 列是 datetime 类型
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    except Exception as e:
        print(f"错误: 转换 'timestamp' 列为 datetime 类型失败: {e}。无法保存到表 '{table_name}'。")
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        # 将 'timestamp' 列设置为索引，这对于 to_sql 和潜在的查询性能有好处
        # 但如果 'timestamp' 和 'symbol' 联合主键的冲突由 to_sql 的 if_exists='replace' 或 UNIQUE约束处理，
        # 则直接写入可能更简单。这里我们使用 'append'，依赖 PRIMARY KEY 来防止重复。
        # df.set_index(['timestamp', 'symbol'], inplace=True) # 如果主键冲突由数据库处理

        # 为了避免可能的 "database is locked" 错误，尤其是在并发写或者IDE自动保存触发脚本时，
        # 可以增加超时时间。
        # conn.execute("PRAGMA journal_mode=WAL;") # WAL模式可以提高并发性，但需要SQLite 3.7.0+
        
        df.to_sql(table_name, conn, if_exists=if_exists, index=False) 
        conn.commit()
        print(f"成功将 {len(df)} 条数据追加到数据库 '{db_path}' 的表 '{table_name}' 中。")

    except sqlite3.IntegrityError as e:
        # 这通常是由于违反了 PRIMARY KEY (timestamp, symbol) 的唯一性约束
        # 如果是由于并发写入相同数据导致的，可以接受，数据已存在。
        print(f"保存数据到表 '{table_name}' 时发生 IntegrityError (可能是重复记录，已忽略): {e}")
        # print("如果你希望覆盖重复记录，请考虑在保存前删除旧数据，或使用不同的 `if_exists`策略 (如 'replace'，但这会替换整个表)。") # 原注释保留参考
    except sqlite3.Error as e:
        print(f"保存DataFrame到数据库表 '{table_name}' 时发生 SQLite错误: {e}") # 更具体的错误类型
    except Exception as e_gen:
        print(f"保存DataFrame时发生未知错误 (表: '{table_name}'): {e_gen}")
    finally:
        if conn:
            conn.close()

def delete_data_from_db(symbols: list, start_date: str, end_date: str, table_name: str, db_path=DB_FILE):
    """
    从指定数据库的指定表中删除特定股票在特定日期范围内的数据。
    确保 start_date 和 end_date 是 'YYYY-MM-DD' 格式的字符串。
    """
    if not symbols:
        print("未提供股票代码，不执行删除操作。")
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 构建占位符 '?' 用于SQL查询中的股票代码列表
        placeholders = ','.join('?' for _ in symbols)
        
        # SQL删除语句
        # 注意: SQLite 的 DATETIME 函数可以直接处理 'YYYY-MM-DD HH:MM:SS' 或 'YYYY-MM-DD' 格式的字符串
        # 为了包含 end_date 当天的数据，我们需要将 end_date 视为当天的结束，即 'YYYY-MM-DD 23:59:59.999'
        # 或者，如果timestamp列存储的是日期，比较可以直接用 date(timestamp)
        # 假设 timestamp 列是 DATETIME 类型
        sql_delete = f"""
        DELETE FROM {table_name}
        WHERE symbol IN ({placeholders})
        AND timestamp >= ? 
        AND timestamp < DATE(?, '+1 day') 
        """
        # 参数包含股票列表，然后是开始日期和结束日期
        params = symbols + [start_date, end_date]
        
        cursor.execute(sql_delete, params)
        conn.commit()
        deleted_rows = cursor.rowcount
        if deleted_rows > 0:
            print(f"成功从表 '{table_name}' 中删除了 {deleted_rows} 条关于 {', '.join(symbols)} 在 {start_date} 到 {end_date} 的旧数据。")
        else:
            print(f"在表 '{table_name}' 中没有找到关于 {', '.join(symbols)} 在 {start_date} 到 {end_date} 范围内的旧数据可供删除。")

    except sqlite3.Error as e:
        print(f"从数据库表 '{table_name}' 删除数据时发生错误: {e}")
    finally:
        if conn:
            conn.close()

def query_data_from_db(symbols: list = None, start_date: str = None, end_date: str = None, 
                       table_name: str = OHLCV_DAILY_TABLE_NAME, # 默认查询日线表
                       db_path=DB_FILE, limit: int = None) -> pd.DataFrame:
    """
    从指定数据库的指定表中查询数据。
    可以按股票代码列表、开始/结束日期进行筛选。
    返回一个 Pandas DataFrame。
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        
        query = f"SELECT timestamp, symbol, open, high, low, close, volume FROM {table_name}"
        conditions = []
        params = []

        if symbols:
            if isinstance(symbols, str): symbols = [symbols]
            placeholders = ','.join('?' for _ in symbols)
            conditions.append(f"symbol IN ({placeholders})")
            params.extend(symbols)
        
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
            
        if end_date:
            # 查询时，通常希望包含end_date当天的数据
            # 如果end_date是'YYYY-MM-DD'，则需要查询到 'YYYY-MM-DD 23:59:59.999'
            # 或者更简单的方式是 timestamp < date(end_date, '+1 day')
            conditions.append("timestamp < DATE(?, '+1 day')")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY timestamp ASC" # 保证数据按时间升序

        if limit and isinstance(limit, int) and limit > 0:
            query += f" LIMIT {limit}" # 注意: LIMIT 不能用 ? 占位符直接绑定

        # print(f"Executing query on table '{table_name}': {query} with params: {params}")
        df = pd.read_sql_query(query, conn, params=params, parse_dates=['timestamp'])
        # print(f"从表 '{table_name}' 查询到 {len(df)} 条数据。")
        return df

    except sqlite3.Error as e:
        print(f"从数据库表 '{table_name}' 查询数据时发生错误: {e}")
        return pd.DataFrame() # 返回空DataFrame
    finally:
        if conn:
            conn.close()

def get_latest_timestamp_from_db(symbol: str, table_name: str, db_path=DB_FILE) -> Optional[datetime]:
    """获取指定股票在指定表中的最新时间戳"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        query = f"SELECT MAX(timestamp) FROM {table_name} WHERE symbol = ?"
        cursor.execute(query, (symbol,))
        result = cursor.fetchone()
        if result and result[0]:
            # SQLite 返回的时间戳字符串可能需要解析
            # pd.to_datetime 可以很好地处理多种格式
            return pd.to_datetime(result[0])
        return None
    except sqlite3.Error as e:
        print(f"从表 '{table_name}' 获取最新时间戳时出错 (symbol: {symbol}): {e}")
        return None
    finally:
        if conn:
            conn.close()

def load_data_from_db(table_name: str = OHLCV_DAILY_TABLE_NAME, 
                      symbols: list = None, 
                      start_date: str = None, 
                      end_date: str = None, 
                      db_path=DB_FILE) -> pd.DataFrame:
    """
    从SQLite数据库加载OHLCV数据。
    可以按股票代码列表和日期范围进行筛选。
    返回的DataFrame会将 'timestamp' 列设为索引。
    """
    try:
        conn = sqlite3.connect(db_path)
        query = f"SELECT * FROM {table_name}"
        conditions = []
        params = []

        if symbols:
            if len(symbols) == 1:
                conditions.append("symbol = ?")
                params.append(symbols[0])
            else:
                placeholders = ', '.join('?' * len(symbols))
                conditions.append(f"symbol IN ({placeholders})")
                params.extend(symbols)
        
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp ASC" # 确保数据按时间排序
        
        df = pd.read_sql_query(query, conn, params=params, parse_dates=['timestamp'])
        
        if df.empty:
            print("从数据库未查询到符合条件的数据。")
            return pd.DataFrame() # 返回空DataFrame

        df.set_index('timestamp', inplace=True)
        print(f"从数据库表 {table_name} 加载了 {len(df)} 条数据。")
        return df

    except sqlite3.Error as e:
        print(f"从数据库加载数据时发生错误: {e}")
        return pd.DataFrame() # 返回空DataFrame
    finally:
        if conn:
            conn.close()

def load_csv_data(file_path: str) -> pd.DataFrame:
    """
    从CSV文件加载股票数据，并将'Date'列解析为日期时间索引。
    (保持原有功能，用于直接读取CSV或作为导入DB的中间步骤)
    """
    try:
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        df.columns = [col.lower() for col in df.columns]
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str)
        print(f"数据从 {file_path} 加载成功 (原始CSV加载器)。")
        return df
    except FileNotFoundError:
        print(f"错误: 文件 {file_path} 未找到 (原始CSV加载器)。")
        return None
    except Exception as e:
        print(f"加载CSV数据时发生错误: {e} (原始CSV加载器)。")
        return None

def import_csv_to_db(csv_file_path: str, table_name: str = OHLCV_DAILY_TABLE_NAME, db_path=DB_FILE):
    """
    将CSV文件中的数据导入到SQLite数据库。
    """
    print(f"开始从 {csv_file_path} 导入数据到数据库表 {table_name}...")
    df = load_csv_data(csv_file_path) # 使用现有的CSV加载器
    if df is not None and not df.empty:
        # load_csv_data 已经将Date设为index，并转为小写列名。
        # save_df_to_db 会处理索引重置和列名'date'->'timestamp'的转换。
        save_df_to_db(df, table_name, db_path)
        print(f"数据从 {csv_file_path} 导入数据库完成。")
    else:
        print(f"未能从 {csv_file_path} 加载数据，导入数据库中止。")

def _delete_all_data_for_symbol(symbol: str, table_name: str, db_path: str = DB_FILE):
    """内部辅助函数，删除指定表中特定symbol的所有数据。"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql_delete = f"DELETE FROM {table_name} WHERE symbol = ?"
        cursor.execute(sql_delete, (symbol,))
        conn.commit()
        deleted_rows = cursor.rowcount
        if deleted_rows > 0:
            print(f"成功从表 '{table_name}' 中删除了 {deleted_rows} 条关于 '{symbol}' 的旧数据。")
        else:
            print(f"在表 '{table_name}' 中没有找到关于 '{symbol}' 的旧数据可供删除。")
    except sqlite3.Error as e:
        print(f"从数据库表 '{table_name}' 删除 '{symbol}' 的所有数据时发生错误: {e}")
    finally:
        if conn:
            conn.close()

def download_and_store_single_stock(
    symbol_to_download: str, 
    yf_period: str = "max", 
    yf_interval: str = "1d", 
    target_table_name: str = OHLCV_DAILY_TABLE_NAME,
    db_path: str = DB_FILE
):
    """
    从 yfinance 下载指定股票的数据，进行预处理，然后删除旧数据并存入数据库。
    """
    print(f"开始下载股票 {symbol_to_download} 的数据 (period: {yf_period}, interval: {yf_interval})...")
    
    try:
        ticker = yf.Ticker(symbol_to_download)
        # auto_adjust=True (默认) 会返回调整后的OHLC，actions=False (默认) 不会单独返回分红和拆股事件
        df = ticker.history(period=yf_period, interval=yf_interval, auto_adjust=True, actions=False)
    except Exception as e:
        print(f"从 yfinance 下载 {symbol_to_download} 数据时出错: {e}")
        return

    if df.empty:
        print(f"未能从 yfinance 下载到 {symbol_to_download} 的数据 (period: {yf_period}, interval: {yf_interval})。")
        return

    print(f"成功从 yfinance 下载了 {len(df)} 条 {symbol_to_download} 的原始数据。开始预处理...")

    # 数据预处理
    df_processed = df.copy()
    df_processed.reset_index(inplace=True) # 将索引 (通常是 Date 或 Datetime) 变成列

    # 重命名日期列为 'timestamp'
    date_col_name = df_processed.columns[0] # 通常是 'Date' 或 'Datetime'
    df_processed.rename(columns={date_col_name: 'timestamp'}, inplace=True)
    
    # 转换 'timestamp' 列为 datetime 对象并确保UTC (yfinance索引通常已经是datetime但可能需明确tz)
    # pd.to_datetime(df_processed['timestamp'])
    # 如果已经是 timezone-aware，保留；如果是 naive，本地化到UTC (yfinance 通常返回tz-aware的UTC时间)
    if df_processed['timestamp'].dt.tz is None:
         df_processed['timestamp'] = df_processed['timestamp'].dt.tz_localize('UTC')
    else:
         df_processed['timestamp'] = df_processed['timestamp'].dt.tz_convert('UTC')


    df_processed['symbol'] = symbol_to_download

    # 将列名转换为小写
    df_processed.columns = [col.lower() for col in df_processed.columns]
    
    # 选取并重排我们需要的列 (确保 volume 列存在，如果yfinance没返回就填充0)
    if 'volume' not in df_processed.columns:
        df_processed['volume'] = 0
        
    required_db_cols = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
    # 检查是否存在所有必需列，防止因yfinance返回数据结构变化导致错误
    missing_cols = [col for col in required_db_cols if col not in df_processed.columns]
    if missing_cols:
        print(f"错误: 从yfinance获取的数据经处理后缺少以下列: {missing_cols}。无法保存。")
        return
        
    df_to_save = df_processed[required_db_cols]

    print(f"数据预处理完成。准备删除旧数据并保存 {len(df_to_save)} 条新数据到表 '{target_table_name}'...")

    _delete_all_data_for_symbol(symbol_to_download, target_table_name, db_path)
    save_df_to_db(df_to_save, target_table_name, db_path)
    print(f"股票 {symbol_to_download} 的数据已成功下载并存储到表 '{target_table_name}'。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="数据库和数据加载工具 (core_engine.data_loader)")
    
    # 添加 action 参数，用于区分不同的操作
    parser.add_argument(
        '--action', 
        type=str, 
        required=True, 
        choices=['init_db', 'download_stock'], 
        help="要执行的操作: 'init_db' (初始化数据库表), 'download_stock' (下载并存储单只股票的历史数据)"
    )
    
    # 参数用于 'download_stock' action
    parser.add_argument(
        '--symbol', 
        type=str, 
        help="要下载的股票代码 (例如 '002594.SZ', 'MSFT'). 'download_stock' action必需."
    )
    parser.add_argument(
        '--period', 
        type=str, 
        default="max", 
        help="yfinance的period参数 (例如 '1y', '5y', 'max'). 默认为 'max'."
    )
    parser.add_argument(
        '--interval', 
        type=str, 
        default="1d", 
        help="yfinance的interval参数 (例如 '1d', '1wk', '1m', '5m'). 默认为 '1d'."
    )
    parser.add_argument(
        '--table', 
        type=str, 
        default=OHLCV_DAILY_TABLE_NAME, 
        help=f"目标数据库表名. 默认为 '{OHLCV_DAILY_TABLE_NAME}'. "
             f"可选: '{OHLCV_MINUTE_TABLE_NAME}' (用于分钟线)."
    )
    parser.add_argument(
        '--db_path',
        type=str,
        default=DB_FILE,
        help=f"数据库文件路径. 默认为 '{DB_FILE}'."
    )

    args = parser.parse_args()

    if args.action == 'init_db':
        print("执行数据库初始化...")
        init_db(args.db_path)
        print("数据库初始化完成。")
    elif args.action == 'download_stock':
        if not args.symbol:
            parser.error("--action 'download_stock' 要求必须提供 --symbol 参数。")
        
        print(f"准备下载股票: {args.symbol}")
        print(f"  Period: {args.period}")
        print(f"  Interval: {args.interval}")
        print(f"  Target Table: {args.table}")
        print(f"  Database: {args.db_path}")
        
        download_and_store_single_stock(
            symbol_to_download=args.symbol,
            yf_period=args.period,
            yf_interval=args.interval,
            target_table_name=args.table,
            db_path=args.db_path
        )
    else:
        print(f"未知的action: {args.action}")
        parser.print_help()

# 示例:
# python -m core_engine.data_loader --action init_db
# python -m core_engine.data_loader --action download_stock --symbol 002594.SZ --period max --interval 1d --table ohlcv_daily_data
# python -m core_engine.data_loader --action download_stock --symbol MSFT --period 1y --interval 1d
# python -m core_engine.data_loader --action download_stock --symbol BTC-USD --period 7d --interval 1m --table ohlcv_1m_data

# 1. 初始化数据库 (会在项目根目录的 data/market_data.db 创建)
# init_db()

# 2. 测试导入 sample_stock_data.csv 到数据库
# sample_csv_file = os.path.join(DATA_DIR, 'sample_stock_data.csv') 
# 确保 sample_stock_data.csv 在 data 目录下，如果不是，需要调整路径或复制文件
# 为了测试，我们假设它在 data 目录下
# if not os.path.exists(sample_csv_file):
#     print(f"警告: 示例CSV文件 {sample_csv_file} 不存在，无法执行导入测试。请确保该文件存在于 {DATA_DIR} 目录中。")
# else:
#     print(f"\n--- 测试CSV导入 ({sample_csv_file}) ---")
#     import_csv_to_db(sample_csv_file)

# 3. 测试从数据库加载所有数据
# print("\n--- 测试从数据库加载所有数据 ---")
# all_db_data = load_data_from_db()
# if not all_db_data.empty:
#     all_db_data.info()
#     print(all_db_data.head())

# 4. 测试按条件从数据库加载数据
# print("\n--- 测试从数据库加载特定股票和日期范围数据 ---")
# 假设 sample_stock_data.csv 包含 STOCK_A 和日期 '2023-01-01' 至 '2023-01-03'
# 注意：日期字符串格式应与数据库中存储的timestamp格式兼容进行比较
# pd.to_datetime能处理多种格式，SQLite中通常是 'YYYY-MM-DD HH:MM:SS'
# stock_a_data = load_data_from_db(symbols=['STOCK_A'], start_date='2023-01-01', end_date='2023-01-03')
# if not stock_a_data.empty:
#     print("\nSTOCK_A 数据 (2023-01-01 to 2023-01-03):")
#     print(stock_a_data)
# else:
#     print("未找到 STOCK_A 在指定日期范围的数据。可能是CSV中无此数据或导入问题。")
    
# stock_b_data = load_data_from_db(symbols=['STOCK_B'])
# if not stock_b_data.empty:
#     print("\nSTOCK_B 全部数据:")
#     print(stock_b_data)
# else:
#     print("未找到 STOCK_B 的数据。")

# print("\n--- data_loader.py 模块测试结束 ---") 
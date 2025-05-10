import pandas as pd
import sqlite3
import os

# --- 数据库配置 ---
DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "market_data.db")
OHLCV_TABLE_NAME = "ohlcv_data"
# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

def init_db(db_path=DB_FILE, table_name=OHLCV_TABLE_NAME):
    """
    初始化数据库，如果表不存在则创建表。
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                timestamp DATETIME NOT NULL,
                symbol TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                PRIMARY KEY (timestamp, symbol)
            )
        ''')
        conn.commit()
        print(f"数据库 {db_path} 初始化成功，表 {table_name} 已确保存在。")
    except sqlite3.Error as e:
        print(f"数据库初始化错误: {e}")
    finally:
        if conn:
            conn.close()

def save_df_to_db(df: pd.DataFrame, table_name: str, db_path=DB_FILE):
    """
    将Pandas DataFrame的数据保存到SQLite数据库的指定表中。
    DataFrame的列名应与数据库表字段匹配。
    'timestamp' 列应为Pandas的datetime类型。
    如果DataFrame的索引是 'timestamp' (或 'Date')，它将被重置为普通列。
    """
    if df.empty:
        print("输入到 save_df_to_db 的 DataFrame 为空，不执行任何操作。")
        return

    # print(f"原始列名 (在 save_df_to_db 入口): {list(df.columns)}") # 早期调试点

    df_to_save = df.copy()

    # 调试代码：检查列的结构
    print("\\n--- Debug: save_df_to_db ---")
    print(f"Incoming DataFrame columns (before lowercasing): {df_to_save.columns}")
    print(f"Type of incoming DataFrame columns: {type(df_to_save.columns)}")
    print("Individual column details (name and type):")
    for i, col_name in enumerate(df_to_save.columns):
        print(f"  Column {i}: '{col_name}', Type: {type(col_name)}")
    print("--- End Debug ---")

    # 确保列名为小写，这与数据库表定义一致
    df_to_save.columns = [col.lower() for col in df_to_save.columns]
    
    original_index_name = None
    if df_to_save.index.name:
        original_index_name = df_to_save.index.name # 保存原始索引名
        df_to_save.reset_index(inplace=True) # 重置索引为列
    
    # 将由索引恢复的列 (可能是 'Date' 或 'date') 重命名为 'timestamp'
    # reset_index 产生的列名与原索引名一致，但load_csv_data设置的是大写Date索引
    if original_index_name and original_index_name.lower() == 'date':
        # 如果原始索引名是 Date 或 date，reset_index后会生成同名列
        df_to_save.rename(columns={original_index_name: 'timestamp'}, inplace=True)
    elif 'date' in df_to_save.columns: # 作为备选，如果有名为'date'的列也重命名
        df_to_save.rename(columns={'date': 'timestamp'}, inplace=True)

    # 检查必要的列是否存在
    required_cols = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
    missing_cols = [col for col in required_cols if col not in df_to_save.columns]
    if missing_cols:
        print(f"错误：DataFrame缺少必要的列: {missing_cols}。无法保存到数据库。")
        return

    # 确保timestamp是datetime类型 (Pandas的to_sql在某些SQLite版本下可能对datetime处理不佳，确保是字符串格式或Pandas datetime)
    # df_to_save['timestamp'] = pd.to_datetime(df_to_save['timestamp'])
    # 对于SQLite, to_sql通常能很好地处理Pandas datetime对象

    try:
        conn = sqlite3.connect(db_path)
        # 使用 'append' 来添加新数据，如果数据已存在（基于主键），则会失败，需要更复杂的逻辑来处理更新或忽略
        # 对于OHLCV数据，通常如果主键冲突，我们可能希望是更新或忽略。 pandas to_sql 不直接支持 ON CONFLICT IGNORE/REPLACE
        # 更稳妥的方式是先删除符合条件的老数据，或者在读取时处理好数据范围避免重复插入，或使用更高级的ORM
        # 此处为了教学简单，我们依赖PRIMARY KEY约束来防止完全相同的行重复插入，但如果只是部分重复则仍会插入。
        # 如果要实现 "upsert" (update or insert) 或 "insert or ignore"，通常需要执行原生SQL。
        # 这里，我们先用 append，并假设数据源头不会有完全重复的 (timestamp, symbol) 对，或者接受插入失败。
        # 或者，更简单的做法是，如果明确是批量导入，先清空相关数据范围的表。
        df_to_save.to_sql(table_name, conn, if_exists='append', index=False)
        print(f"{len(df_to_save)} 条数据成功保存到数据库表 {table_name}。")
    except sqlite3.IntegrityError as e:
        print(f"保存数据到数据库时发生完整性错误 (可能是主键冲突): {e}")
    except Exception as e:
        print(f"保存数据到数据库时发生错误: {e}")
    finally:
        if conn:
            conn.close()


def load_data_from_db(table_name: str = OHLCV_TABLE_NAME, 
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

def import_csv_to_db(csv_file_path: str, table_name: str = OHLCV_TABLE_NAME, db_path=DB_FILE):
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

def delete_data_from_db(symbols: list, start_date: str, end_date: str, 
                          db_path=DB_FILE, table_name=OHLCV_TABLE_NAME):
    """
    从数据库中删除指定股票列表在指定日期范围内的数据。

    参数:
    symbols (list): 股票代码列表 (例如 ['AAPL', 'MSFT'])
    start_date (str): 开始日期 (YYYY-MM-DD)，包含此日期。
    end_date (str): 结束日期 (YYYY-MM-DD)，包含此日期。
    db_path (str): 数据库文件路径。
    table_name (str): 数据表名。
    """
    if not symbols:
        print("未提供股票代码，不执行删除操作。")
        return

    deleted_rows_count = 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 构建股票代码的占位符
        symbol_placeholders = ', '.join('?' * len(symbols))
        params = list(symbols)
        
        sql_delete_query = f"DELETE FROM {table_name} WHERE symbol IN ({symbol_placeholders})"
        
        if start_date:
            sql_delete_query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            sql_delete_query += " AND timestamp <= ?"
            params.append(end_date)
            
        cursor.execute(sql_delete_query, tuple(params))
        deleted_rows_count = cursor.rowcount
        conn.commit()
        if deleted_rows_count > 0:
            print(f"从表 '{table_name}' 中成功删除了 {symbols} 在 {start_date if start_date else '最早'} 到 {end_date if end_date else '最新'} 范围内的 {deleted_rows_count} 条旧数据。")
        else:
            print(f"在表 '{table_name}' 中未找到与 {symbols} 在 {start_date if start_date else '最早'} 到 {end_date if end_date else '最新'} 范围匹配的旧数据进行删除。")

    except sqlite3.Error as e:
        print(f"从数据库删除数据时发生错误: {e}")
    finally:
        if conn:
            conn.close()
    return deleted_rows_count

if __name__ == '__main__':
    print("--- data_loader.py 模块测试 ---")
    # 1. 初始化数据库 (会在项目根目录的 data/market_data.db 创建)
    init_db()

    # 2. 测试导入 sample_stock_data.csv 到数据库
    sample_csv_file = os.path.join(DATA_DIR, 'sample_stock_data.csv') 
    # 确保 sample_stock_data.csv 在 data 目录下，如果不是，需要调整路径或复制文件
    # 为了测试，我们假设它在 data 目录下
    if not os.path.exists(sample_csv_file):
        print(f"警告: 示例CSV文件 {sample_csv_file} 不存在，无法执行导入测试。请确保该文件存在于 {DATA_DIR} 目录中。")
    else:
        print(f"\n--- 测试CSV导入 ({sample_csv_file}) ---")
        import_csv_to_db(sample_csv_file)

    # 3. 测试从数据库加载所有数据
    print("\n--- 测试从数据库加载所有数据 ---")
    all_db_data = load_data_from_db()
    if not all_db_data.empty:
        all_db_data.info()
        print(all_db_data.head())

    # 4. 测试按条件从数据库加载数据
    print("\n--- 测试从数据库加载特定股票和日期范围数据 ---")
    # 假设 sample_stock_data.csv 包含 STOCK_A 和日期 '2023-01-01' 至 '2023-01-03'
    # 注意：日期字符串格式应与数据库中存储的timestamp格式兼容进行比较
    # pd.to_datetime能处理多种格式，SQLite中通常是 'YYYY-MM-DD HH:MM:SS'
    stock_a_data = load_data_from_db(symbols=['STOCK_A'], start_date='2023-01-01', end_date='2023-01-03')
    if not stock_a_data.empty:
        print("\nSTOCK_A 数据 (2023-01-01 to 2023-01-03):")
        print(stock_a_data)
    else:
        print("未找到 STOCK_A 在指定日期范围的数据。可能是CSV中无此数据或导入问题。")
    
    stock_b_data = load_data_from_db(symbols=['STOCK_B'])
    if not stock_b_data.empty:
        print("\nSTOCK_B 全部数据:")
        print(stock_b_data)
    else:
        print("未找到 STOCK_B 的数据。")

    print("\n--- data_loader.py 模块测试结束 ---") 
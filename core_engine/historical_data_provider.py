from typing import List, Optional, Dict, Any
import datetime
import pandas as pd
import yfinance as yf # 取消注释
import sqlite3
import time
import os
import asyncio
from datetime import timezone, timedelta

# 从data_loader导入表名常量
# 假设 historical_data_provider.py 和 data_loader.py 在同一个 core_engine 包中
try:
    from .data_loader import DB_FILE, OHLCV_MINUTE_TABLE_NAME, OHLCV_DAILY_TABLE_NAME
    from .data_loader import save_df_to_db, delete_data_from_db # 新增导入
except ImportError:
    # Fallback for scenarios where relative import might fail (e.g. direct script run for testing, though unlikely for this file)
    print("Warning: Relative import of data_loader constants failed. Ensure correct package structure.")
    # Define fallbacks if necessary, though this provider relies кризисно on these constants
    DB_FILE = "../data/market_data.db" # Adjust if necessary as a fallback
    OHLCV_MINUTE_TABLE_NAME = "ohlcv_1m_data"
    OHLCV_DAILY_TABLE_NAME = "ohlcv_daily_data"


# DB_FILE is now imported from data_loader
# DB_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'market_data.db') 

RECENT_DATA_THRESHOLD_DAYS = 7 # 定义"近期数据"的时间阈值（天）

def _interval_to_pandas_rule_and_seconds(interval_str: str) -> tuple[Optional[str], int, Optional[str]]:
    """
    Converts API interval string to Pandas resampling rule, interval duration in seconds,
    and yfinance interval string.
    Returns: (pandas_rule, interval_seconds, yfinance_interval)
    Raises: ValueError if interval_str is not supported.
    Now returns Optional[str] for rules and yf_interval as yf part might not always be relevant.
    """
    if interval_str == "1m":
        return "1min", 60, "1m"
    elif interval_str == "5m":
        return "5min", 300, "5m"
    elif interval_str == "15m":
        return "15min", 900, "15m"
    elif interval_str == "30m":
        return "30min", 1800, "30m"
    elif interval_str == "1h":
        return "H", 3600, "1h" # yfinance also accepts "60m"
    elif interval_str == "1d":
        return "D", 86400, "1d"
    else:
        # Log a warning, but let the API layer handle detailed error response to client
        print(f"[HistProv] Unsupported interval string provided to core function: {interval_str}. Will attempt to proceed if it matches a pandas rule like 'D'.")
        # Try to see if it directly matches a pandas rule if it's for daily or longer, yf_interval can be None
        if interval_str.endswith('D') or interval_str.endswith('W') or interval_str.endswith('M'):
             # A simple heuristic, this might need more robust parsing for arbitrary pandas rules
             # For simplicity, we assume only very basic daily/weekly/monthly might be passed if not standard
             return interval_str, 0, None # interval_seconds 0 indicates unknown/don't care for non-standard
        # raise ValueError(f"Unsupported interval string provided to core function: {interval_str}")
        return None, 0, None

# Helper to resample and format DataFrame
def _resample_and_format_df(df: pd.DataFrame, pd_interval_str: str, symbol: str, interval_str: str) -> pd.DataFrame:
    if df.empty:
        return df
    # Ensure DataFrame index is DatetimeIndex in UTC
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'time' in df.columns:
            try:
                # Assuming 'time' is UNIX timestamp in seconds. Convert to datetime objects.
                df['time'] = pd.to_datetime(df['time'], unit='s', utc=False) # Initially naive
                df = df.set_index('time')
            except Exception as e:
                print(f"[HistProv][_resample_and_format_df] Error converting 'time' column for {symbol}: {e}")
                return pd.DataFrame()
        else:
            print(f"[HistProv][_resample_and_format_df] 'time' column not found for index for {symbol}.")
            return pd.DataFrame()
    
    # Localize to UTC if naive, or convert if already localized but not UTC
    if df.index.tz is None:
        df = df.tz_localize('UTC')
    else:
        df = df.tz_convert('UTC')

    print(f"[HistProv][_resample_and_format_df] Resampling {symbol} to {pd_interval_str} from {len(df)} records. Input columns: {df.columns.tolist()}")
    
    # Expect lowercase columns now
    required_cols = {'open', 'high', 'low', 'close'}
    if not required_cols.issubset(df.columns):
        print(f"[HistProv][_resample_and_format_df] Missing required ohlc columns (expected lowercase) for {symbol}. Available: {df.columns.tolist()}")
        return pd.DataFrame()

    aggregation_rules = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
    }
    if 'volume' in df.columns:
        aggregation_rules['volume'] = 'sum'
    else: 
        df['volume'] = 0 
        aggregation_rules['volume'] = 'sum'

    try:
        df_resampled = df.resample(pd_interval_str).agg(aggregation_rules)
        df_resampled = df_resampled.dropna(subset=['open']) # Drop rows where 'open' is NaN (implies no trades in interval)
    except Exception as e:
        print(f"[HistProv][_resample_and_format_df] Error during resampling for {symbol} to {pd_interval_str}: {e}")
        return pd.DataFrame()
        
    print(f"[HistProv][_resample_and_format_df] Resampled {symbol} to {len(df_resampled)} records.")
    return df_resampled

async def fetch_historical_klines_core(
    symbol: str, 
    interval_str: str, 
    limit: int, 
    end_time_ts: Optional[int] = None,
    source_preference: str = "db_then_yahoo" # 修改默认值，或在API层决定
) -> List[Dict]:
    
    df_yf_raw: pd.DataFrame = pd.DataFrame() # Initialize df_yf_raw

    pd_interval_str, interval_seconds, yf_interval_for_fetch = _interval_to_pandas_rule_and_seconds(interval_str) # 获取yf_interval
    if pd_interval_str is None:
        print(f"[HistProv] Invalid or unhandled interval: {interval_str} for symbol {symbol}. Returning empty list.")
        return []

    requested_end_dt_utc = datetime.datetime.now(timezone.utc)
    if end_time_ts:
        requested_end_dt_utc = datetime.datetime.fromtimestamp(end_time_ts, timezone.utc)

    source_table_to_query = OHLCV_DAILY_TABLE_NAME 
    fetch_raw_interval_for_resampling = "1d" 
    target_table_for_saving_yf_data = OHLCV_DAILY_TABLE_NAME # 表名，用于保存从yf下载的数据
    yf_interval_to_fetch_raw = "1d" # 从 yfinance 获取数据的原始粒度

    is_minute_request = interval_str.endswith(('m', 'H', 'T')) # 更简洁的检查
    
    print(f"[HistProv] Request for {symbol}@{interval_str}. End time: {requested_end_dt_utc}. Is minute request: {is_minute_request}")

    if is_minute_request:
        threshold_date_utc = datetime.datetime.now(timezone.utc) - timedelta(days=RECENT_DATA_THRESHOLD_DAYS)
        if requested_end_dt_utc > threshold_date_utc:
            print(f"[HistProv] Request is for recent minute data. DB target: {OHLCV_MINUTE_TABLE_NAME}.")
            source_table_to_query = OHLCV_MINUTE_TABLE_NAME
            fetch_raw_interval_for_resampling = "1m"
            target_table_for_saving_yf_data = OHLCV_MINUTE_TABLE_NAME
            yf_interval_to_fetch_raw = "1m" # 如果是分钟级请求，尝试获取1分钟原始数据
        else:
            print(f"[HistProv] Request is for older minute data (older than {RECENT_DATA_THRESHOLD_DAYS} days). DB target: {OHLCV_DAILY_TABLE_NAME}.")
            # 对于非常旧的分钟数据，仍从日线重采样，但下载时可以考虑获取日线
            target_table_for_saving_yf_data = OHLCV_DAILY_TABLE_NAME # 保存到日线表
            yf_interval_to_fetch_raw = "1d"

    else: # Daily, Weekly, Monthly request
        print(f"[HistProv] Request is for daily or longer interval. DB target: {OHLCV_DAILY_TABLE_NAME}.")
        source_table_to_query = OHLCV_DAILY_TABLE_NAME
        fetch_raw_interval_for_resampling = "1d"
        target_table_for_saving_yf_data = OHLCV_DAILY_TABLE_NAME
        yf_interval_to_fetch_raw = "1d"

    # Ensure yf_interval_for_fetch is set if we intend to fetch from yfinance
    # Override yf_interval_to_fetch_raw based on what _interval_to_pandas_rule_and_seconds gave for yfinance
    # For minute data, we always want to fetch '1m' from yfinance if possible.
    # For daily+ data, yf_interval_for_fetch (from _interval_to_pandas_rule_and_seconds based on interval_str) should be fine.
    if is_minute_request:
        yf_final_fetch_interval = "1m" # Always try to get 1m for minute requests
    elif yf_interval_for_fetch: # e.g. "1d", "1wk"
        yf_final_fetch_interval = yf_interval_for_fetch
    else: # Fallback if yf_interval_for_fetch was None (e.g. for custom daily rules like "2D")
        yf_final_fetch_interval = "1d"


    base_interval_seconds_for_query_estimation = 60 
    if source_table_to_query == OHLCV_DAILY_TABLE_NAME:
        base_interval_seconds_for_query_estimation = 86400 
    
    estimated_base_points_needed = (interval_seconds * limit) / base_interval_seconds_for_query_estimation if base_interval_seconds_for_query_estimation > 0 else limit
    # estimated_seconds_needed = estimated_base_points_needed * base_interval_seconds_for_query_estimation
    estimated_seconds_needed = interval_seconds * limit if interval_seconds > 0 else 86400 * limit * (30 if pd_interval_str.endswith('M') else (7 if pd_interval_str.endswith('W') else 1))


    limit_multiplier = max(1.5, interval_seconds / base_interval_seconds_for_query_estimation if base_interval_seconds_for_query_estimation > 0 and interval_seconds > 0 else 1.5)
    query_limit_for_raw_data = int(limit * limit_multiplier) 
    if query_limit_for_raw_data < 200: query_limit_for_raw_data = 200 

    start_dt_utc_for_query = requested_end_dt_utc - timedelta(seconds=query_limit_for_raw_data * base_interval_seconds_for_query_estimation if base_interval_seconds_for_query_estimation > 0 else estimated_seconds_needed * 1.5)


    print(f"[HistProv] DB Read: Table='{source_table_to_query}', Symbol='{symbol}', TargetEnd='{requested_end_dt_utc}', QueryStart='{start_dt_utc_for_query}'")

    klines_data: List[Dict] = []
    df_to_process: pd.DataFrame = pd.DataFrame()

    # 1. Attempt to fetch from DB
    if "db" in source_preference: # e.g., "db_only", "db_then_yahoo"
        df_db = await asyncio.to_thread(
            _fetch_from_db_sync, 
            source_table_to_query, 
            symbol, 
            start_dt_utc_for_query,
            requested_end_dt_utc
        )
        if df_db is not None and not df_db.empty:
            print(f"[HistProv] DB Hit: Found {len(df_db)} raw records for {symbol} in {source_table_to_query}.")
            df_to_process = df_db
        else:
            print(f"[HistProv] DB Miss: No records found for {symbol} in {source_table_to_query} for the query time range.")

    # DIAGNOSTIC LOGS
    print(f"[HistProv DEBUG] Before Yahoo fetch check: df_to_process.empty is {df_to_process.empty}, source_preference is '{source_preference}'")

    # 2. If DB is empty or preference allows Yahoo, try fetching from Yahoo Finance
    # A more sophisticated check for "data sufficiency" could be added here later.
    # For now, if df_to_process is empty and we can use Yahoo, we fetch.
    if df_to_process.empty and "yahoo" in source_preference: # e.g., "db_then_yahoo", "yahoo_only"
        print(f"[HistProv] DB data insufficient or not preferred. Attempting fetch from Yahoo Finance for {symbol}@{yf_final_fetch_interval}.")
        
        # Determine start_time for yfinance fetch
        # We want 'limit' number of 'interval_str' klines.
        # yf_start_time should be far enough back to get enough raw data for this.
        # If yf_final_fetch_interval is '1m', we need limit * (interval_seconds / 60) 1-minute bars.
        yf_base_interval_seconds, _, _ = _interval_to_pandas_rule_and_seconds(yf_final_fetch_interval)
        yf_base_interval_seconds = yf_base_interval_seconds[1] if isinstance(yf_base_interval_seconds, tuple) else 60 # get seconds from tuple or default for "1m"

        # Calculate how many yf_final_fetch_interval periods are in one target interval_str period
        ratio_target_to_yf_raw = interval_seconds / yf_base_interval_seconds if yf_base_interval_seconds > 0 else 1
        num_yf_raw_bars_needed = int(limit * ratio_target_to_yf_raw * 1.5) # Fetch 1.5x estimated raw yf bars
        if num_yf_raw_bars_needed < 200 : num_yf_raw_bars_needed = 200 # Min fetch

        # yf_duration_needed = timedelta(seconds=num_yf_raw_bars_needed * yf_base_interval_seconds)
        # yf_fetch_start_time = requested_end_dt_utc - yf_duration_needed
        
        # Simpler yf_fetch_start_time, similar to db query logic, but based on yf_final_fetch_interval
        yf_fetch_start_time = requested_end_dt_utc - timedelta(seconds=num_yf_raw_bars_needed * yf_base_interval_seconds)


        df_yf_raw = await asyncio.to_thread(
            _fetch_from_yfinance_sync,
            symbol,
            yf_final_fetch_interval, # Fetch at this granularity (e.g., "1m" or "1d")
            yf_fetch_start_time,
            requested_end_dt_utc,
            num_yf_raw_bars_needed, # Pass a target number of raw bars
            yf_base_interval_seconds 
        )

        if df_yf_raw is not None and not df_yf_raw.empty:
            print(f"[HistProv] Yahoo Hit: Fetched {len(df_yf_raw)} raw records for {symbol}@{yf_final_fetch_interval} from Yahoo Finance.")
            
            # Prepare df_yf_raw for saving to DB and processing
            df_yf_to_save = df_yf_raw.copy()
            df_yf_to_save.reset_index(inplace=True) # Move DatetimeIndex to a column
            # yfinance returns 'Datetime' or 'Date' as index name, to_datetime converts it
            df_yf_to_save.rename(columns={df_yf_to_save.columns[0]: 'timestamp'}, inplace=True) 
            df_yf_to_save['timestamp'] = pd.to_datetime(df_yf_to_save['timestamp'], utc=True)
            df_yf_to_save['symbol'] = symbol
            
            # Ensure lowercase column names as expected by save_df_to_db
            df_yf_to_save.columns = [col.lower() for col in df_yf_to_save.columns]
            
            # Select only columns needed for save_df_to_db
            cols_for_db = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
            df_yf_to_save = df_yf_to_save[[col for col in cols_for_db if col in df_yf_to_save.columns]]

            if not df_yf_to_save.empty and 'timestamp' in df_yf_to_save.columns and 'symbol' in df_yf_to_save.columns:
                print(f"[HistProv] Saving {len(df_yf_to_save)} fetched Yahoo Finance records to {target_table_for_saving_yf_data} for {symbol}.")
                
                # Convert datetime to string for delete_data_from_db if it expects strings
                # yf_fetch_start_time and requested_end_dt_utc are already datetime objects
                # delete_data_from_db takes 'YYYY-MM-DD' strings.
                # We should delete a slightly wider range than fetched to be safe, or precisely the fetched range.
                # For simplicity, let's use the min/max timestamp from the fetched data.
                min_ts_to_delete = df_yf_to_save['timestamp'].min().strftime('%Y-%m-%d %H:%M:%S')
                max_ts_to_delete = df_yf_to_save['timestamp'].max().strftime('%Y-%m-%d %H:%M:%S')

                # It's better to delete based on the actual data fetched to avoid deleting too much or too little.
                # Convert to 'YYYY-MM-DD' for delete_data_from_db
                delete_start_date_str = df_yf_to_save['timestamp'].min().strftime('%Y-%m-%d')
                delete_end_date_str = df_yf_to_save['timestamp'].max().strftime('%Y-%m-%d')

                print(f"[HistProv] Deleting existing data for {symbol} in {target_table_for_saving_yf_data} between {delete_start_date_str} and {delete_end_date_str} before saving new Yahoo data.")
                await asyncio.to_thread(
                    delete_data_from_db,
                    symbols=[symbol],
                    start_date=delete_start_date_str,
                    end_date=delete_end_date_str,
                    table_name=target_table_for_saving_yf_data
                )
                
                await asyncio.to_thread(
                    save_df_to_db, 
                    df_yf_to_save, 
                    target_table_for_saving_yf_data
                )
                # After saving, df_to_process should be this new data.
                # We need to ensure it's in the same format as df_db (e.g. 'time' column, potentially indexed by 'time')
                # For now, let _fetch_from_db_sync re-fetch it to ensure consistency in format for _resample_and_format_df
                # Or, re-format df_yf_to_save to match what _fetch_from_db_sync would return
                
                # Re-format df_yf_raw to match df_db for subsequent processing
                # df_yf_raw has DatetimeIndex. _fetch_from_db_sync returns df with 'time' column.
                # _resample_and_format_df can handle both DatetimeIndex or 'time' column.
                # Let's ensure df_yf_raw has lowercase column names as expected by _resample_and_format_df.
                df_yf_raw.columns = [col.lower() for col in df_yf_raw.columns]
                df_to_process = df_yf_raw

            else:
                print(f"[HistProv] Fetched Yahoo data for {symbol} was empty or malformed after processing for DB save.")
        else:
            print(f"[HistProv] Yahoo Miss: No data fetched from Yahoo Finance for {symbol}@{yf_final_fetch_interval}.")
    
    # 3. Process the data (either from DB or from Yahoo)
    if df_to_process is not None and not df_to_process.empty:
        # Ensure 'time' column exists if index is not already DatetimeIndex for _resample_and_format_df
        # _fetch_from_db_sync renames 'timestamp' to 'time'.
        # If df_to_process came from df_yf_raw, it has a DatetimeIndex.
        # _resample_and_format_df should handle both cases.
        
        print(f"[HistProv] Processing {len(df_to_process)} raw records for {symbol} (Source: {'Yahoo' if df_to_process is df_yf_raw else 'DB'}). Raw interval for resampling: {fetch_raw_interval_for_resampling}")
        
        # If df_to_process is from Yahoo (df_yf_raw), its index is DatetimeIndex and columns are lowercase.
        # If df_to_process is from DB (df_db), it has 'time' column from 'timestamp'.
        # _resample_and_format_df expects DatetimeIndex or 'time' column and lowercase ohlcv columns.
        
        df_resampled = _resample_and_format_df(df_to_process, pd_interval_str, symbol, interval_str) 
        
        if not df_resampled.empty:
            if limit > 0 and len(df_resampled) > limit:
                df_resampled = df_resampled.iloc[-limit:]
            
            print(f"[HistProv] Resampled to {len(df_resampled)} records for {symbol}@{interval_str} (limit applied). Final df index type: {type(df_resampled.index)}")

            for timestamp_val, row in df_resampled.iterrows():
                # Ensure timestamp_val is a proper pd.Timestamp if not already
                if not isinstance(timestamp_val, pd.Timestamp):
                     # This case should ideally not happen if _resample_and_format_df ensures DatetimeIndex
                     # but as a safeguard:
                    try:
                        timestamp_val = pd.Timestamp(timestamp_val)
                    except Exception as e_ts:
                        print(f"[HistProv] Error converting timestamp {timestamp_val} to pd.Timestamp: {e_ts}. Skipping row.")
                        continue
                
                # Convert to UTC if naive, or ensure it is UTC
                if timestamp_val.tzinfo is None:
                    timestamp_val = timestamp_val.tz_localize('UTC')
                elif timestamp_val.tzinfo != timezone.utc:
                    timestamp_val = timestamp_val.tz_convert(timezone.utc)

                klines_data.append({
                    "time": int(timestamp_val.timestamp()), # Ensure UTC timestamp
                    "open": row["open"],   # Use lowercase key
                    "high": row["high"],  # Use lowercase key
                    "low": row["low"],    # Use lowercase key
                    "close": row["close"], # Use lowercase key
                    "volume": row.get("volume", 0) # Use lowercase key
                })
        else:
             print(f"[HistProv] DataFrame for {symbol} from {source_table_to_query} was empty after resampling to {interval_str}.")
    else:
        print(f"[HistProv] No klines data produced for {symbol}@{interval_str} from {source_table_to_query}. Returning empty list.")
    
    return klines_data

# --- Database Fetching Logic --- 
def _fetch_from_db_sync(
    table_name: str, # Added table_name parameter
    current_symbol: str, 
    db_start_time: datetime.datetime, 
    db_end_time: datetime.datetime
) -> pd.DataFrame:
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE) # DB_FILE is now imported
        # Ensure datetime objects are naive for SQLite query if they are timezone-aware
        # SQLite typically stores datetimes as text or numbers and doesn't handle tz natively.
        # Comparisons are done lexicographically or numerically.
        # It's often best to store all datetimes in DB as UTC naive, then convert on read.
        # Our _resample_and_format_df localizes to UTC if naive, or converts if already tz-aware.
        # So, for querying, ensure start/end are comparable to what's in DB.
        # If DB stores UTC naive (as ISO format strings), convert query times to UTC naive strings.
        
        start_date_str_utc_naive = db_start_time.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        end_date_str_utc_naive = db_end_time.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        query = f"""
            SELECT timestamp, open, high, low, close, volume
            FROM {table_name}  -- Use the passed table_name
            WHERE symbol = ? AND timestamp >= ? AND timestamp < ? 
            ORDER BY timestamp ASC
        """ 
        # Params for query: symbol, start_datetime_str, end_datetime_str
        # print(f"[DB_SYNC] Querying {table_name} for {current_symbol} from {start_date_str_utc_naive} to {end_date_str_utc_naive}")
        df = pd.read_sql_query(query, conn, params=(current_symbol, start_date_str_utc_naive, end_date_str_utc_naive),
                               parse_dates=['timestamp'])

        if df.empty:
            print(f"[HistProv][DB] No data found in {table_name} for {current_symbol} in range {start_date_str_utc_naive} - {end_date_str_utc_naive}")
            return pd.DataFrame()

        # The 'timestamp' column from read_sql_query with parse_dates will be naive datetime objects (or UTC if stored as such and driver handles it).
        # _resample_and_format_df will handle timezone localization/conversion to UTC.
        # We rename to 'time' here to match what _resample_and_format_df expects if it doesn't find a DatetimeIndex.
        df.rename(columns={'timestamp': 'time'}, inplace=True)
        
        print(f"[HistProv][DB] Fetched {len(df)} raw rows from {table_name} for {current_symbol}. Renamed 'timestamp' to 'time'.")
        return df

    except sqlite3.Error as e_sql:
        print(f"[HistProv][DB] SQLite error for {current_symbol} in {table_name}: {e_sql}")
        return pd.DataFrame()
    except Exception as e_pd:
        print(f"[HistProv][DB] Pandas/general error for {current_symbol} in {table_name}: {e_pd}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

# --- yfinance Fetching Logic (Fallback) ---
# This section is no longer used if source_preference is always db-related
# Consider removing or refactoring if yfinance direct fetch is ever needed again here.
# For now, it remains as dead code if not called.
def _fetch_from_yfinance_sync(
    yf_symbol: str, 
    yf_interval_str: str, 
    yf_start_time: datetime.datetime, 
    yf_end_time: datetime.datetime,
    target_limit: int, # Renamed from target_limit for clarity
    target_interval_seconds: int # Renamed from target_interval_seconds
) -> pd.DataFrame:
    try:
        # yfinance usually performs better if start/end are just dates for daily, 
        # or more precise for intraday. Max history for intraday is limited.
        # For intraday <60 days, use start/end. For >60 days, period is better but might not give exact start.
        # Given we have end_time and a limit, we can estimate a start.
        # yfinance intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        
        # Adjust start time for yfinance query; it can be tricky with intraday history limits.
        # Fetch a bit more to be safe and then trim.
        # For yfinance, end_time is exclusive for intraday, inclusive for daily.
        # Let's make our query end time inclusive by adding a small delta if it's not daily.
        yf_query_end_time = yf_end_time
        if yf_interval_str not in ["1d", "5d", "1wk", "1mo", "3mo"]:
             yf_query_end_time = yf_end_time + timedelta(seconds=target_interval_seconds) # Use direct timedelta

        # Estimate start time for yfinance query
        # yfinance can be fussy about start/end for very fine intervals over long periods.
        # Let's try to fetch roughly target_limit * 1.5 records initially.
        # estimated_yf_duration = timedelta(seconds=target_limit * target_interval_seconds * 1.5) 
        # yf_query_start_time = yf_end_time - estimated_yf_duration
        
        # Use the passed yf_start_time directly. It's calculated upstream.
        yf_query_start_time = yf_start_time
        
        # Cap yfinance intraday query range (e.g., max 59 days for 1m)
        # This capping might be too aggressive if yf_start_time was carefully calculated.
        # Consider removing or making it conditional. For now, retain with a log.
        max_days_for_1m = 59
        max_days_for_gt_1m_lt_1d = 720 # yfinance actual limit is 730 days
        
        if yf_interval_str == "1m":
            if (yf_query_end_time - yf_query_start_time).days > max_days_for_1m:
                print(f"[HistProv][YF] Warning: Query for {yf_symbol}@{yf_interval_str} ({ (yf_query_end_time - yf_query_start_time).days } days) exceeds typical {max_days_for_1m}-day limit for yfinance 1m. Adjusting start time.")
                yf_query_start_time = yf_query_end_time - timedelta(days=max_days_for_1m)
        elif yf_interval_str not in ["1d", "5d", "1wk", "1mo", "3mo"]: # Intraday other than 1m
            if (yf_query_end_time - yf_query_start_time).days > max_days_for_gt_1m_lt_1d:
                print(f"[HistProv][YF] Warning: Query for {yf_symbol}@{yf_interval_str} ({ (yf_query_end_time - yf_query_start_time).days } days) exceeds typical {max_days_for_gt_1m_lt_1d}-day limit for yfinance intraday. Adjusting start time.")
                yf_query_start_time = yf_query_end_time - timedelta(days=max_days_for_gt_1m_lt_1d)


        print(f"[HistProv][YF] Querying yfinance for {yf_symbol} interval {yf_interval_str} from {yf_query_start_time} to {yf_query_end_time}")

        df_yf = yf.download(
            tickers=yf_symbol, 
            start=yf_query_start_time, 
            end=yf_query_end_time, # yfinance end is exclusive for intraday
            interval=yf_interval_str,
            progress=False,
        )

        if df_yf.empty:
            print(f"[HistProv][YF] No data returned from yfinance for {yf_symbol} after download call.") # 更明确的日志
            return pd.DataFrame()

        print(f"[HistProv][YF] yf.download for {yf_symbol} returned {len(df_yf)} rows. Columns: {df_yf.columns.tolist()}")
        # print(f"[HistProv][YF] df_yf.head():\n{df_yf.head()}") # 可以取消注释以查看数据头

        # Ensure UTC timezone and rename columns
        if df_yf.index.tz is None:
            df_yf.index = df_yf.index.tz_localize('UTC')
        else:
            df_yf.index = df_yf.index.tz_convert('UTC')
        
        # Handle MultiIndex columns if present (e.g., [('Open', 'MSFT'), ...])
        if isinstance(df_yf.columns, pd.MultiIndex):
            print(f"[HistProv][YF] Detected MultiIndex columns: {df_yf.columns.tolist()}. Flattening.")
            # Flatten MultiIndex columns: use the first level (e.g., 'Open' from ('Open', 'MSFT'))
            df_yf.columns = df_yf.columns.get_level_values(0)
            print(f"[HistProv][YF] Columns after flattening MultiIndex: {df_yf.columns.tolist()}")

        df_yf.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }, inplace=True)
        
        # Select only necessary columns
        # df_yf = df_yf[['open', 'high', 'low', 'close', 'volume']] # Ensure these are lowercase from rename
        df_yf = df_yf[['open', 'high', 'low', 'close', 'volume']].copy() # Use .copy() to avoid SettingWithCopyWarning
        df_yf.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)

        print(f"[HistProv][YF] Fetched {len(df_yf)} rows from yfinance for {yf_symbol}")
        return df_yf

    except Exception as e_yf:
        print(f"[HistProv][YF] Error during yfinance fetch or processing for {yf_symbol}: {e_yf}") # 修改日志
        # 尝试打印df_yf的状态，即使在异常中
        if 'df_yf' in locals() and df_yf is not None:
            print(f"[HistProv][YF] df_yf state at time of exception: Empty={df_yf.empty}")
            if not df_yf.empty:
                print(f"[HistProv][YF] df_yf columns at exception: {df_yf.columns.tolist()}")
                # print(f"[HistProv][YF] df_yf.head() at exception:\n{df_yf.head()}")
        else:
            print("[HistProv][YF] df_yf was not defined or None at time of exception.")
        return pd.DataFrame()

# ... (rest of the file, including _fetch_from_db_sync and _fetch_from_yfinance_sync) ... 
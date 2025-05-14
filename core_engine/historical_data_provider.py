from typing import List, Optional, Dict, Any
import datetime
import pandas as pd
# import yfinance as yf # yfinance is not directly used in this file anymore for fetching, only for _interval_to_pandas_rule_and_seconds potentially
import sqlite3
import time
import os
import asyncio
from datetime import timezone, timedelta

# 从data_loader导入表名常量
# 假设 historical_data_provider.py 和 data_loader.py 在同一个 core_engine 包中
try:
    from .data_loader import DB_FILE, OHLCV_MINUTE_TABLE_NAME, OHLCV_DAILY_TABLE_NAME
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
        return "T", 60, "1m"
    elif interval_str == "5m":
        return "5T", 300, "5m"
    elif interval_str == "15m":
        return "15T", 900, "15m"
    elif interval_str == "30m":
        return "30T", 1800, "30m"
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
    source_preference: str = "db_only" # This param might be less relevant now, or re-purposed
) -> List[Dict]:
    
    pd_interval_str, interval_seconds, _ = _interval_to_pandas_rule_and_seconds(interval_str)
    if pd_interval_str is None:
        print(f"[HistProv] Invalid or unhandled interval: {interval_str} for symbol {symbol}. Returning empty list.")
        return []

    requested_end_dt_utc = datetime.datetime.now(timezone.utc)
    if end_time_ts:
        requested_end_dt_utc = datetime.datetime.fromtimestamp(end_time_ts, timezone.utc)

    # Determine data source table and base interval for fetching
    source_table_to_query = OHLCV_DAILY_TABLE_NAME # Default to daily data
    fetch_raw_interval_for_resampling = "1d" # Default: assume we fetch daily to resample

    is_minute_request = interval_str.endswith('m') or interval_str.endswith('H') or interval_str.endswith('T')
    
    print(f"[HistProv] Request for {symbol}@{interval_str}. End time: {requested_end_dt_utc}. Is minute request: {is_minute_request}")

    if is_minute_request:
        # Check if the request end time is within our recent threshold for minute data
        threshold_date_utc = datetime.datetime.now(timezone.utc) - timedelta(days=RECENT_DATA_THRESHOLD_DAYS)
        if requested_end_dt_utc > threshold_date_utc:
            print(f"[HistProv] Request is for recent minute data. Attempting to use {OHLCV_MINUTE_TABLE_NAME}.")
            source_table_to_query = OHLCV_MINUTE_TABLE_NAME
            fetch_raw_interval_for_resampling = "1m" # We'll fetch 1m data to resample
        else:
            print(f"[HistProv] Request is for older minute data (older than {RECENT_DATA_THRESHOLD_DAYS} days). Will use {OHLCV_DAILY_TABLE_NAME} and resample.")
    else: # Daily, Weekly, Monthly request
        print(f"[HistProv] Request is for daily or longer interval. Using {OHLCV_DAILY_TABLE_NAME}.")
        source_table_to_query = OHLCV_DAILY_TABLE_NAME
        fetch_raw_interval_for_resampling = "1d"

    # Estimate query window based on the TARGET interval and limit
    # If we fetch 1m to resample to 1h, and limit is 100 (1h bars), we need 100 * 60 = 6000 1m bars.
    base_interval_seconds_for_query_estimation = 60 # Assume 1m if using minute table
    if source_table_to_query == OHLCV_DAILY_TABLE_NAME:
        base_interval_seconds_for_query_estimation = 86400 # Assume 1d if using daily table
    
    # Heuristic for query window: fetch more raw data points than the final limit might suggest,
    # especially if resampling from finer to coarser granularity.
    # If target interval is `interval_seconds` and limit is `limit`,
    # total seconds for final output is `interval_seconds * limit`.
    # Number of base data points needed is `(interval_seconds * limit) / base_interval_seconds_for_query_estimation`
    estimated_base_points_needed = (interval_seconds * limit) / base_interval_seconds_for_query_estimation
    estimated_seconds_needed = estimated_base_points_needed * base_interval_seconds_for_query_estimation 
                                 # This simplifies to interval_seconds * limit, which is the duration of the final output data.
                                 # We need to fetch data covering AT LEAST this duration of raw points.
    if interval_seconds == 0: # Handle non-standard daily/weekly/monthly from _interval_to_pandas_rule_and_seconds
        estimated_seconds_needed = 86400 * limit * (30 if pd_interval_str.endswith('M') else (7 if pd_interval_str.endswith('W') else 1)) # Rough estimate

    # Fetch a bit more to be safe, e.g., 1.5x to 2x the estimated duration or number of points
    # query_duration_seconds = estimated_seconds_needed * 2.0 # Fetch 2x the duration
    # More robust: if limit is 200 bars of 5min, that's 1000 minutes. We need 1000 1-min bars. Fetch 1500-2000 1-min bars.
    # A simpler heuristic for now: multiply limit by a factor based on resampling ratio
    limit_multiplier = max(1.5, interval_seconds / base_interval_seconds_for_query_estimation if base_interval_seconds_for_query_estimation > 0 else 1.5)
    query_limit_for_raw_data = int(limit * limit_multiplier) if interval_seconds > 0 else limit * 2 # Fetch more raw data points
    if query_limit_for_raw_data < 200: query_limit_for_raw_data = 200 # Fetch at least a decent chunk

    # Calculate query start time based on the raw data points we need
    start_dt_utc_for_query = requested_end_dt_utc - timedelta(seconds=query_limit_for_raw_data * base_interval_seconds_for_query_estimation)

    print(f"[HistProv] Fetching K-lines for {symbol}@{interval_str} from table '{source_table_to_query}'.")
    print(f"         Target end: {requested_end_dt_utc}, Query start for raw: {start_dt_utc_for_query}, Estimated raw points to fetch: {query_limit_for_raw_data}")

    klines_data: List[Dict] = []

    df_db = await asyncio.to_thread(
        _fetch_from_db_sync, 
        source_table_to_query, # Pass the determined table name
        symbol, 
        start_dt_utc_for_query,
        requested_end_dt_utc
    )

    if df_db is not None and not df_db.empty:
        print(f"[HistProv] Found {len(df_db)} raw records for {symbol} in {source_table_to_query} (raw interval: {fetch_raw_interval_for_resampling}).")
        # Pass the original requested interval_str for final resampling target
        df_resampled = _resample_and_format_df(df_db, pd_interval_str, symbol, interval_str) 
        
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
        print(f"[HistProv] No records found for {symbol} in {source_table_to_query} for the query time range.")
    
    if not klines_data:
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
    target_limit: int,
    target_interval_seconds: int
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
        estimated_yf_duration = timedelta(seconds=target_limit * target_interval_seconds * 1.5) # Use direct timedelta
        yf_query_start_time = yf_end_time - estimated_yf_duration
        
        # Cap yfinance intraday query range (e.g., max 59 days for 1m)
        if yf_interval_str == "1m" and (yf_end_time - yf_query_start_time) > timedelta(days=59): # Use direct timedelta
            yf_query_start_time = yf_end_time - timedelta(days=59) # Use direct timedelta
        elif yf_interval_str in ["5m", "15m", "30m"] and (yf_end_time - yf_query_start_time) > timedelta(days=720): # Approx 2 years for >1m intraday # Use direct timedelta
            # yfinance has 730 days limit for intervals > 1m and < 1d.
             yf_query_start_time = yf_end_time - timedelta(days=720) # Use direct timedelta

        print(f"[historical_data_provider_yf] Querying yfinance for {yf_symbol} interval {yf_interval_str} from {yf_query_start_time} to {yf_query_end_time}")

        df_yf = yf.download(
            tickers=yf_symbol, 
            start=yf_query_start_time, 
            end=yf_query_end_time, # yfinance end is exclusive for intraday
            interval=yf_interval_str,
            progress=False,
            show_errors=True
        )

        if df_yf.empty:
            print(f"[historical_data_provider_yf] No data returned from yfinance for {yf_symbol}")
            return pd.DataFrame()

        # Ensure UTC timezone and rename columns
        if df_yf.index.tz is None:
            df_yf.index = df_yf.index.tz_localize('UTC')
        else:
            df_yf.index = df_yf.index.tz_convert('UTC')
        
        df_yf.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }, inplace=True)
        
        # Select only necessary columns
        df_yf = df_yf[['open', 'high', 'low', 'close', 'volume']]
        df_yf.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)

        print(f"[historical_data_provider_yf] Fetched {len(df_yf)} rows from yfinance for {yf_symbol}")
        return df_yf

    except Exception as e_yf:
        print(f"[historical_data_provider_yf] Error fetching from yfinance for {yf_symbol}: {e_yf}")
        return pd.DataFrame()

# ... (rest of the file, including _fetch_from_db_sync and _fetch_from_yfinance_sync) ... 
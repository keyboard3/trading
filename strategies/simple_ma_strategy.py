import pandas as pd

def dual_moving_average_strategy(data: pd.DataFrame, short_window: int, long_window: int, symbol_col: str = 'symbol', close_col: str = 'close'):
    """
    为给定的数据应用双均线交叉策略，并为每个股票代码独立计算。

    参数:
    data (pd.DataFrame): 包含OHLCV数据的DataFrame，必须有日期索引，
                         以及指定的收盘价列和股票代码列。
    short_window (int): 短期移动平均线的窗口期。
    long_window (int): 长期移动平均线的窗口期。
    symbol_col (str): DataFrame中表示股票代码的列名。默认为'symbol'。
    close_col (str): DataFrame中表示收盘价的列名。默认为'close'。

    返回:
    pd.DataFrame: 带有 'short_ma', 'long_ma', 和 'signal' 列的原始DataFrame。
                  'signal' 列: 1 表示买入, -1 表示卖出, 0 表示持有。
    """
    if not isinstance(data, pd.DataFrame):
        raise ValueError("输入数据必须是 Pandas DataFrame。")
    if short_window <= 0 or long_window <= 0:
        raise ValueError("均线窗口期必须为正整数。")
    if short_window >= long_window:
        raise ValueError("短期均线窗口必须小于长期均线窗口。")
    if close_col not in data.columns:
        raise ValueError(f"收盘价列 '{close_col}' 不在DataFrame中。")
    if symbol_col not in data.columns:
        # 如果没有symbol列，则假设数据是单一资产
        print(f"警告: 股票代码列 '{symbol_col}' 未找到。将数据视为单一资产处理。")
        temp_symbol_col = '_temp_symbol_'
        data[temp_symbol_col] = 'DEFAULT_ASSET' # 创建一个临时的symbol列
        result_df = _apply_ma_strategy_to_group(data.copy(), short_window, long_window, close_col, temp_symbol_col)
        result_df.drop(columns=[temp_symbol_col], inplace=True)
        return result_df

    # 按股票代码分组，并对每个组应用策略
    processed_groups = []
    for symbol, group_data in data.groupby(symbol_col):
        # print(f"正在处理股票代码: {symbol}")
        processed_group = _apply_ma_strategy_to_group(group_data.copy(), short_window, long_window, close_col, symbol_col)
        processed_groups.append(processed_group)

    if not processed_groups:
        return data # 如果没有数据或分组，返回原始数据

    # 合并处理后的分组
    final_df = pd.concat(processed_groups)
    return final_df.sort_index() # 按日期索引排序，以防万一

def _apply_ma_strategy_to_group(group_data: pd.DataFrame, short_window: int, long_window: int, close_col: str, symbol_col: str):
    """辅助函数，对单个股票代码的数据应用MA策略"""
    
    # 计算短期和长期移动平均线
    # 使用 .rolling().mean() 计算简单移动平均线 (SMA)
    group_data['short_ma'] = group_data[close_col].rolling(window=short_window, min_periods=1).mean()
    group_data['long_ma'] = group_data[close_col].rolling(window=long_window, min_periods=1).mean()

    # 生成信号
    # 初始信号为0 (持有)
    group_data['signal'] = 0
    
    # 当短期均线上穿长期均线时，产生买入信号 (1)
    # 条件1: 当前 short_ma > long_ma
    # 条件2: 上一个时间点的 short_ma <= long_ma
    buy_condition = (group_data['short_ma'] > group_data['long_ma']) & \
                    (group_data['short_ma'].shift(1) <= group_data['long_ma'].shift(1))
    group_data.loc[buy_condition, 'signal'] = 1

    # 当短期均线下穿长期均线时，产生卖出信号 (-1)
    # 条件1: 当前 short_ma < long_ma
    # 条件2: 上一个时间点的 short_ma >= long_ma
    sell_condition = (group_data['short_ma'] < group_data['long_ma']) & \
                     (group_data['short_ma'].shift(1) >= group_data['long_ma'].shift(1))
    group_data.loc[sell_condition, 'signal'] = -1
    
    # 填充因shift(1)操作产生的初始NaN信号（如果有必要，但这里交叉条件已处理）
    # group_data['signal'].fillna(0, inplace=True) # 通常不需要，因为我们初始化为0

    return group_data

if __name__ == '__main__':
    # 简单的测试代码
    # 构造一个示例 DataFrame (模拟 data_loader.py 的输出)
    sample_data = {
        'Date': pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05',
                                '2023-01-06', '2023-01-07', '2023-01-08', '2023-01-09', '2023-01-10',
                                '2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05',
                                '2023-01-06', '2023-01-07', '2023-01-08', '2023-01-09', '2023-01-10']),
        'close': [10, 12, 11, 13, 15, 14, 16, 18, 17, 19,
                  20, 18, 19, 17, 16, 15, 14, 13, 12, 11],
        'open': [9, 11, 10, 12, 14, 13, 15, 17, 16, 18,
                 21, 19, 18, 16, 17, 16, 15, 14, 13, 12 ],
        'symbol': ['AAA'] * 10 + ['BBB'] * 10
    }
    df = pd.DataFrame(sample_data)
    df.set_index('Date', inplace=True)

    print("原始数据:")
    print(df)

    # 应用策略
    short_w = 3
    long_w = 6
    df_with_signals = dual_moving_average_strategy(df.copy(), short_window=short_w, long_window=long_w) # 使用默认列名 'close' 和 'symbol'
    
    print(f"\n应用MA策略 (short_w={short_w}, long_w={long_w}) 后的数据:")
    print(df_with_signals[['symbol', 'close', 'short_ma', 'long_ma', 'signal']])

    # 测试无symbol列的情况
    df_single = df[df['symbol'] == 'AAA'].drop(columns=['symbol'])
    print("\n原始数据 (单一资产, 无symbol列):")
    print(df_single)
    df_single_with_signals = dual_moving_average_strategy(df_single.copy(), short_window=short_w, long_window=long_w)
    print(f"\n应用MA策略 (单一资产) 后的数据:")
    print(df_single_with_signals[['close', 'short_ma', 'long_ma', 'signal']]) 
import pandas as pd
import numpy as np

def _calculate_rsi_values(close_prices: pd.Series, period: int = 14) -> pd.Series:
    """
    计算给定收盘价序列的RSI值。

    参数:
    close_prices (pd.Series): 收盘价格序列。
    period (int): RSI 计算的周期长度，默认为14。

    返回:
    pd.Series: 包含RSI值的序列，索引与输入序列一致。
    """
    if not isinstance(close_prices, pd.Series):
        raise TypeError("输入 close_prices 必须是 pandas Series。")
    if close_prices.empty:
        return pd.Series(dtype=np.float64, index=close_prices.index) # 返回空的RSI Series

    # 1. 计算价格变化
    delta = close_prices.diff()

    # 2. 分离上涨和下跌
    gain = pd.Series(np.where(delta > 0, delta, 0), index=close_prices.index)
    loss = pd.Series(np.where(delta < 0, -delta, 0), index=close_prices.index)

    # 3. 计算平均上涨和平均下跌 (使用Wilder's smoothing / EWMA)
    # Wilder's smoothing (alpha = 1/N) 等价于 ewm(com=N-1)
    avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()

    # 4. 计算相对强度 (RS)
    # 避免除以0的情况
    rs = avg_gain / avg_loss
    
    # 5. 计算RSI
    rsi = 100.0 - (100.0 / (1.0 + rs))
    
    # 处理特殊情况：当 avg_loss 为 0 时
    # 如果 avg_gain > 0 且 avg_loss == 0, rs 为 inf, rsi 应该为 100.
    # 如果 avg_gain == 0 且 avg_loss == 0 (例如，价格在周期内无变化), rs 为 NaN, rsi 应该为中性值(如50)或NaN。
    # pandas的 1.0 / (1.0 + np.inf) 结果是 0.0, 所以 rsi = 100.0，这是正确的。
    # 当 rs 是 NaN (因为 avg_gain 和 avg_loss 都是0), rsi 也是 NaN。这是合理的，因为没有足够信息。
    # 可以考虑在rs为0（avg_gain为0，avg_loss > 0）时rsi为0。100 - (100 / (1+0)) = 0，也是正确的。
    
    # 如果需要将 avg_gain 和 avg_loss 都为0时产生的NaN RSI视作50 (中性):
    # rsi.loc[avg_gain.eq(0) & avg_loss.eq(0) & rsi.isna()] = 50.0
    # 但通常让它保持NaN，表示数据不足或无波动。

    return rsi

def rsi_strategy(data: pd.DataFrame, period: int = 14, 
                 oversold_threshold: float = 30, 
                 overbought_threshold: float = 70) -> pd.DataFrame:
    """
    根据相对强弱指数 (RSI) 生成交易信号。

    参数:
    data (pd.DataFrame): 输入数据，必须包含 'close' 列。
    period (int): RSI 计算的周期长度，默认为14。
    oversold_threshold (float): 超卖阈值，默认为30。
    overbought_threshold (float): 超买阈值，默认为70。

    返回:
    pd.DataFrame: 包含原始数据以及新增 'rsi' 和 'signal' 列的DataFrame。
                  'signal' 列: 1 表示买入, -1 表示卖出, 0 表示持有。
    """
    if 'close' not in data.columns:
        raise ValueError("输入数据 DataFrame 中必须包含 'close' 列")
    if not isinstance(data, pd.DataFrame):
        raise TypeError("输入 data 必须是 pandas DataFrame。")

    df = data.copy()

    # 使用新的辅助函数计算RSI值
    df['rsi'] = _calculate_rsi_values(df['close'], period)
    
    # 6. 生成交易信号
    # 简单信号逻辑：当RSI上穿超卖线时买入，下穿超买线时卖出
    df['signal'] = 0
    # 上一日的RSI值，用于判断交叉
    df['rsi_prev'] = df['rsi'].shift(1)

    # 买入信号：前一日RSI <= 超卖线 AND 当前RSI > 超卖线
    buy_condition = (df['rsi_prev'] <= oversold_threshold) & (df['rsi'] > oversold_threshold)
    df.loc[buy_condition, 'signal'] = 1

    # 卖出信号：前一日RSI >= 超买线 AND 当前RSI < 超买线
    sell_condition = (df['rsi_prev'] >= overbought_threshold) & (df['rsi'] < overbought_threshold)
    df.loc[sell_condition, 'signal'] = -1
    
    # 移除辅助列
    df.drop(columns=['rsi_prev'], inplace=True, errors='ignore')

    return df

if __name__ == '__main__':
    # --- 创建一个模拟的 DataFrame 来测试 ---
    dates = pd.to_datetime([
        '2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05',
        '2023-01-06', '2023-01-07', '2023-01-08', '2023-01-09', '2023-01-10',
        '2023-01-11', '2023-01-12', '2023-01-13', '2023-01-14', '2023-01-15',
        '2023-01-16', '2023-01-17', '2023-01-18', '2023-01-19', '2023-01-20',
        '2023-01-21', '2023-01-22', '2023-01-23', '2023-01-24', '2023-01-25'
    ])
    close_prices_list = [ # Renamed to avoid conflict with pd.Series name
        100, 102, 101, 103, 105, 104, 106, 108, 110, 107, # 持续上涨
        105, 103, 100, 98,  95,  93,  90,  92,  94,  97,  # 下跌后反弹
        95,  93,  90, 88, 85 # 持续下跌
    ]
    sample_data = pd.DataFrame(data={'close': close_prices_list}, index=dates)

    print("--- 测试 RSI 策略模块 (重构后) ---")
    print("原始数据 (部分):")
    print(sample_data.head())

    # 测试 _calculate_rsi_values 函数
    print("\n--- 测试 _calculate_rsi_values ---")
    rsi_series = _calculate_rsi_values(sample_data['close'], period=14)
    print("RSI Series (部分):")
    print(rsi_series.tail(15))
    
    # 验证RSI值
    if rsi_series.notna().any():
        print(f"RSI Series min: {rsi_series.min():.2f}, max: {rsi_series.max():.2f}")
        assert rsi_series.dropna().between(0, 100).all(), "RSI值 (from _calculate_rsi_values) 超出0-100范围"
        print("RSI值 (from _calculate_rsi_values) 验证通过 (在0-100之间，排除NaN)。")
    else:
        print("RSI Series (from _calculate_rsi_values) 全为NaN，无法验证范围。")


    # 测试 rsi_strategy 函数 (现在使用 _calculate_rsi_values)
    print("\n--- 测试 rsi_strategy (使用重构的RSI计算) ---")
    rsi_data_default = rsi_strategy(sample_data.copy())
    print("\n应用RSI策略后 (默认参数, period=14, os=30, ob=70) - 部分数据:")
    print(rsi_data_default.tail(15))
    print("\n产生的信号 (默认参数):")
    print(rsi_data_default[rsi_data_default['signal'] != 0])

    # 测试不同参数
    rsi_data_short = rsi_strategy(sample_data.copy(), period=7, oversold_threshold=25, overbought_threshold=75)
    print("\n应用RSI策略后 (period=7, os=25, ob=75) - 部分数据:")
    print(rsi_data_short.tail(15))
    print("\n产生的信号 (period=7):")
    print(rsi_data_short[rsi_data_short['signal'] != 0])
    
    # 测试RSI值是否在0-100之间 (排除NaN) from rsi_strategy output
    print(f"\nRSI (默认, from rsi_strategy) min: {rsi_data_default['rsi'].min():.2f}, max: {rsi_data_default['rsi'].max():.2f}")
    if rsi_data_default['rsi'].notna().any():
        assert rsi_data_default['rsi'].dropna().between(0, 100).all(), "RSI值 (from rsi_strategy) 超出0-100范围"
        print("RSI值 (默认, from rsi_strategy) 验证通过 (在0-100之间，排除NaN)。")
    else:
        print("RSI值 (默认, from rsi_strategy) 全为NaN，无法验证范围。")

    print("\n--- RSI 策略模块测试结束 (重构后) ---") 
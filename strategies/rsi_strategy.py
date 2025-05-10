import pandas as pd
import numpy as np

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

    df = data.copy()

    # 1. 计算价格变化
    delta = df['close'].diff()

    # 2. 分离上涨和下跌
    # gain = delta.where(delta > 0, 0)
    # loss = -delta.where(delta < 0, 0)
    # 更精确的写法，确保第一个NaN不影响后续计算的对齐
    gain = pd.Series(np.where(delta > 0, delta, 0), index=df.index)
    loss = pd.Series(np.where(delta < 0, -delta, 0), index=df.index)

    # 3. 计算平均上涨和平均下跌 (使用Wilder's smoothing / EWMA)
    # 初始的N日简单平均
    # avg_gain_initial = gain.rolling(window=period, min_periods=period).mean().iloc[period-1]
    # avg_loss_initial = loss.rolling(window=period, min_periods=period).mean().iloc[period-1]
    # df['avg_gain'] = np.nan
    # df['avg_loss'] = np.nan
    # df['avg_gain'].iloc[period-1] = avg_gain_initial
    # df['avg_loss'].iloc[period-1] = avg_loss_initial
    # for i in range(period, len(df)):
    #     df['avg_gain'].iloc[i] = (df['avg_gain'].iloc[i-1] * (period - 1) + gain.iloc[i]) / period
    #     df['avg_loss'].iloc[i] = (df['avg_loss'].iloc[i-1] * (period - 1) + loss.iloc[i]) / period

    # 使用 pandas.ewm 更简洁地实现 Wilder's smoothing
    # Wilder's smoothing (alpha = 1/N) 等价于 ewm(com=N-1)
    avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()

    # 4. 计算相对强度 (RS)
    # 避免除以0的情况，如果 avg_loss 为0，RS应为无穷大 (RSI 接近100)
    rs = avg_gain / avg_loss
    rs.replace([np.inf, -np.inf], np.nan, inplace=True) # 处理avg_loss为0导致的inf
    # 如果avg_loss为0, avg_gain > 0 => rs = inf => rsi = 100
    # 如果avg_loss为0, avg_gain = 0 => rs = nan (因为0/0) => rsi = ? (pandas 处理方式)
    # 我们可以在计算RSI时处理这种情况，或者直接将rs为nan且avg_gain>0的情况设为很大的数

    # 5. 计算RSI
    # rsi = 100 - (100 / (1 + rs))
    # 更稳健的 RSI 计算，处理 RS 为 NaN (因 avg_loss 为 0 导致) 的情况
    df['rsi'] = 100 - (100 / (1 + rs))
    # 当 avg_loss 为 0 时：
    # 如果 avg_gain > 0, rs 为 inf, 1/(1+inf) -> 0, rsi -> 100.
    # 如果 avg_gain = 0 (即 delta连续N期或更多为0或负), avg_gain ewm 可能为0, rs 为 0/0 -> NaN.
    #   此时，如果严格按公式，RS = 0 (因为没有上涨), RSI = 0.
    #   或者，若前N期全为下跌，则avg_gain=0, avg_loss>0 => RS=0 => RSI=0
    #   若前N期全为上涨，则avg_gain>0, avg_loss=0 => RS=inf => RSI=100 (pandas已处理)
    #   若前N期全无变化，则avg_gain=0, avg_loss=0 => RS=NaN, RSI=NaN (pandas已处理)
    #   我们需要确保 RSI 在 [0, 100] 区间内，并且在 avg_loss 为 0 且 avg_gain 为 0 时表现合理 (例如 RSI 为 50 或 0)
    #   实际上，ewm(adjust=False) 在开始阶段如果值全为0，会输出0。如果delta连续为0，gain和loss都是0，avg_gain和avg_loss也是0，rs是nan，rsi是nan。
    #   如果一段时期完全没有价格变动，RSI应该是中性的，比如50。但标准公式在avg_gain=avg_loss=0时会导致NaN。
    #   对于这种情况，一种处理是如果 rs is NaN and avg_gain == 0 and avg_loss == 0，则 RSI = 50 (中性)
    #   但更常见的做法是，如果 avg_loss 是0，则 RSI 几乎是100（除非 avg_gain 也是0）。
    #   如果 avg_gain 是0 且 avg_loss 是0 (例如，价格在期初没有变化)，RSI 应该为 NaN，直到有足够数据。
    #   pandas 的 ewm 应该能优雅处理这些情况， NaN 会在早期出现。
    
    # 传统定义下，如果 avg_loss = 0, 那么 RSI = 100 (除非 avg_gain 也为0，此时 RSI 未定义或视为 0 或 50)
    # 如果 rs 为 NaN (因为 avg_loss 和 avg_gain 都为0, 例如初始N期没有价格变动), 则 RSI 为 NaN.
    # 如果 rs 为 NaN (因为 avg_loss 为 0 而 avg_gain > 0), pandas的 1/(1+inf) 会是0, RSI会是100.
    # 我们需要确保 RSI 不会因为 avg_loss 非常接近0而跳到极端值，ewm应能平滑此行为。

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

    # print(df.tail())
    # print(df[df['signal'] != 0].head())
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
    close_prices = [
        100, 102, 101, 103, 105, 104, 106, 108, 110, 107, # 持续上涨
        105, 103, 100, 98,  95,  93,  90,  92,  94,  97,  # 下跌后反弹
        95,  93,  90, 88, 85 # 持续下跌
    ]
    sample_data = pd.DataFrame(data={'close': close_prices}, index=dates)

    print("--- 测试 RSI 策略模块 ---")
    print("原始数据 (部分):")
    print(sample_data.head())

    # 测试默认参数
    rsi_data_default = rsi_strategy(sample_data.copy())
    print("\\n应用RSI策略后 (默认参数, period=14, os=30, ob=70) - 部分数据:")
    print(rsi_data_default.tail(15)) # 打印最后15条，更容易看到RSI值和信号
    print("\\n产生的信号 (默认参数):")
    print(rsi_data_default[rsi_data_default['signal'] != 0])

    # 测试不同参数
    rsi_data_short = rsi_strategy(sample_data.copy(), period=7, oversold_threshold=25, overbought_threshold=75)
    print("\\n应用RSI策略后 (period=7, os=25, ob=75) - 部分数据:")
    print(rsi_data_short.tail(15))
    print("\\n产生的信号 (period=7):")
    print(rsi_data_short[rsi_data_short['signal'] != 0])
    
    # 测试RSI值是否在0-100之间 (排除NaN)
    print(f"\\nRSI (默认) min: {rsi_data_default['rsi'].min():.2f}, max: {rsi_data_default['rsi'].max():.2f}")
    if rsi_data_default['rsi'].notna().any():
        assert rsi_data_default['rsi'].dropna().between(0, 100).all(), "RSI值超出0-100范围"
        print("RSI值 (默认) 验证通过 (在0-100之间，排除NaN)。")
    else:
        print("RSI值 (默认) 全为NaN，无法验证范围。")

    print("\\n--- RSI 策略模块测试结束 ---") 
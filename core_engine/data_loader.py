import pandas as pd

def load_csv_data(file_path):
    """
    从CSV文件加载股票数据，并将'Date'列解析为日期时间索引。

    参数:
    file_path (str): CSV文件的路径。

    返回:
    pandas.DataFrame: 包含股票数据的DataFrame，以日期为索引。
                     如果文件不存在或解析失败，则返回None。
    """
    try:
        # 读取CSV文件
        df = pd.read_csv(file_path)

        # 将 'Date' 列转换为 datetime 对象
        df['Date'] = pd.to_datetime(df['Date'])

        # 将 'Date' 列设为索引
        df.set_index('Date', inplace=True)

        # 可以选择对列名进行标准化，例如全部小写
        df.columns = [col.lower() for col in df.columns]
        
        # 如果有 'symbol' 列，确保它是字符串类型
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str)

        print(f"数据从 {file_path} 加载成功。")
        return df
    except FileNotFoundError:
        print(f"错误: 文件 {file_path} 未找到。")
        return None
    except Exception as e:
        print(f"加载数据时发生错误: {e}")
        return None

if __name__ == '__main__':
    # 一个简单的测试，当直接运行此文件时执行
    sample_file = '../data/sample_stock_data.csv' # 注意相对路径
    data_df = load_csv_data(sample_file)

    if data_df is not None:
        print("\nDataFrame 信息:")
        data_df.info()
        print("\nDataFrame 前5行:")
        print(data_df.head())
        
        # 如果有symbol列，可以按symbol分组看看
        if 'symbol' in data_df.columns:
            print("\n按symbol分组后的数据量:")
            print(data_df.groupby('symbol').size()) 
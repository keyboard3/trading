import React, { useState } from 'react';

export interface BacktestResultItem { 
  ticker: string;
  metrics: Record<string, string | number>;
  report_url?: string;
  portfolio_value_chart_url?: string; 
  strategy_chart_url?: string; 
  error?: string;
}
export interface BacktestResponse { 
  status: string;
  message?: string;
  run_id?: string;
  results?: BacktestResultItem[];
  run_id_tag?: string;
  results_base_url?: string;
  results_per_symbol?: BacktestResultItem[];
}

interface RunBacktestButtonProps {
  strategyId: string | null;
  stockSymbols: string;
  startDate: string;
  endDate: string;
  parameters: Record<string, any>;
  onBacktestComplete: (response: BacktestResponse | null, error?: string) => void;
}

const RunBacktestButton: React.FC<RunBacktestButtonProps> = ({
  strategyId,
  stockSymbols,
  startDate,
  endDate,
  parameters,
  onBacktestComplete,
}) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleRunBacktest = async () => {
    if (!strategyId) {
      alert('请先选择一个交易策略！');
      onBacktestComplete(null, '未选择策略');
      return;
    }
    if (!stockSymbols.trim()) {
      alert('请输入至少一个股票代码！');
      onBacktestComplete(null, '未输入股票代码');
      return;
    }

    const tickersArray = stockSymbols.split(',').map(s => s.trim()).filter(s => s);
    if (tickersArray.length === 0) {
      alert('请输入有效的股票代码！');
      onBacktestComplete(null, '股票代码无效');
      return;
    }

    const requestBody = {
      strategy_id: strategyId,
      tickers: tickersArray,
      start_date: startDate,
      end_date: endDate,
      parameters: parameters,
    };

    setIsLoading(true);
    onBacktestComplete(null); 

    try {
      const response = await fetch('/api/v1/backtest/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      const responseData = await response.json();

      if (!response.ok) {
        const errorMessage = responseData?.message || responseData?.detail || `回测请求失败，状态码: ${response.status}`;
        throw new Error(errorMessage);
      }
      
      const successfulData: BacktestResponse = {
        status: 'success',
        message: responseData.message,
        run_id: responseData.run_id_tag,
        results: responseData.results_per_symbol,
        run_id_tag: responseData.run_id_tag,
        results_base_url: responseData.results_base_url,
        results_per_symbol: responseData.results_per_symbol
      };
      onBacktestComplete(successfulData);

    } catch (error) {
      console.error('回测API调用失败或处理响应出错:', error);
      const errorMessage = error instanceof Error ? error.message : '执行回测时发生未知错误';
      onBacktestComplete(null, errorMessage);
      alert(`错误: ${errorMessage}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <button
      onClick={handleRunBacktest}
      className={`w-full mt-8 px-6 py-3 border border-transparent rounded-md shadow-sm text-base font-medium text-white`}
      style={{
        backgroundColor: isLoading ? 'gray' : 'lightblue',
        cursor: isLoading ? 'not-allowed' : 'pointer',
      }}
    >
      {isLoading ? '正在执行回测...' : '运行回测'}
    </button>
  );
};

export default RunBacktestButton; 
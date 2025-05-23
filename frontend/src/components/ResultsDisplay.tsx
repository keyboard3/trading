import React from 'react';
import type { BacktestResponse, BacktestResultItem } from './RunBacktestButton';

interface ResultsDisplayProps {
  response: BacktestResponse | null;
  error: string | null;
}

const ResultsDisplay: React.FC<ResultsDisplayProps> = ({ response, error }) => {
  if (error) {
    return (
      <div className="mt-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
        <p className="font-bold">错误:</p>
        <p>{error}</p>
      </div>
    );
  }

  if (!response) {
    return null; // 或者显示 "等待回测结果..."
  }

  if (response.status !== 'success') {
    return (
      <div className="mt-6 p-4 bg-yellow-100 border border-yellow-400 text-yellow-700 rounded">
        <p className="font-bold">回测提示:</p>
        <p>{response.message || '回测执行遇到问题，但未返回明确错误信息。'}</p>
        {response.run_id_tag && <p className="text-sm">运行ID: {response.run_id_tag}</p>}
      </div>
    );
  }

  // 确保 results_per_symbol 是一个数组
  const resultsList = Array.isArray(response.results_per_symbol) ? response.results_per_symbol : [];

  return (
    <div className="p-6 bg-white shadow-lg rounded-md max-w-4xl mx-auto text-left">

      {resultsList.length === 0 && !response.message && (
         <p className="text-gray-600">没有返回具体的回测结果条目。</p>
      )}

      {resultsList.map((item, index) => (
        <div key={item.ticker || index} className="mb-6 p-4 border border-gray-200 rounded-lg shadow-sm bg-gray-50">
          <h3 className="text-xl font-semibold text-blue-700 mb-3">{item.ticker || '未知股票'}</h3>
          
          {item.error && (
            <div className="my-2 p-3 bg-red-50 border border-red-300 text-red-600 rounded">
              <p className="font-bold">此股票回测错误:</p>
              <p>{item.error}</p>
            </div>
          )}

          {!item.error && (
            <>
              <div className="mb-3">
                <h4 className="text-md font-semibold text-gray-700 mb-1">性能指标:</h4>
                {item.metrics && Object.keys(item.metrics).length > 0 ? (
                  <ul className="list-disc list-inside pl-4 text-sm text-gray-600 space-y-1">
                    {Object.entries(item.metrics).map(([key, value]) => (
                      <li key={key}>
                        <span className="font-medium">{key}:</span> {typeof value === 'number' ? value.toFixed(4) : value}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">无可用指标。</p>
                )}
              </div>

              <div className="mb-3">
                <h4 className="text-md font-semibold text-gray-700 mb-1">报告与图表:</h4>
                {item.report_url && (
                  <p className="text-sm">
                    <a 
                      href={item.report_url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      查看详细回测报告
                    </a>
                  </p>
                )}
                {item.portfolio_value_chart_url && (
                  <div className="my-3">
                    <h5 className="text-sm font-semibold text-gray-600 mb-1">投资组合净值曲线:</h5>
                    <img 
                      src={item.portfolio_value_chart_url} 
                      alt="投资组合净值曲线图" 
                      className="w-full h-auto border rounded shadow-sm"
                    />
                  </div>
                )}
                {item.strategy_chart_url && (
                  <div className="my-3">
                    <h5 className="text-sm font-semibold text-gray-600 mb-1">策略信号图:</h5>
                    <img 
                      src={item.strategy_chart_url} 
                      alt="策略信号图" 
                      className="w-full h-auto border rounded shadow-sm"
                    />
                  </div>
                )}
                {!item.report_url && !item.portfolio_value_chart_url && !item.strategy_chart_url && (
                    <p className="text-sm text-gray-500">无可用报告或图表链接。</p>
                )}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
};

export default ResultsDisplay; 
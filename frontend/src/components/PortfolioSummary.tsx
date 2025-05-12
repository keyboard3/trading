import React from 'react';
import type { PortfolioStatusResponse } from '../types';

interface PortfolioSummaryProps {
  portfolioStatus?: PortfolioStatusResponse;
  isActuallyRunning?: boolean;
  isLoading: boolean;
  error?: string | null;
}

const PortfolioSummary: React.FC<PortfolioSummaryProps> = ({ portfolioStatus, isActuallyRunning, isLoading, error }) => {
  if (isLoading) {
    return <div className="p-4 bg-gray-700 rounded-lg shadow text-white">投资组合摘要加载中...</div>;
  }

  if (error) {
    return <div className="p-4 bg-red-700 rounded-lg shadow text-white">错误: {error}</div>;
  }

  if (!portfolioStatus) {
    return <div className="p-4 bg-gray-700 rounded-lg shadow text-white">无投资组合数据。</div>;
  }

  const displayRunningStatus = typeof isActuallyRunning === 'boolean' ? isActuallyRunning : portfolioStatus.is_running;

  const formatCurrency = (value: number) => {
    return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  return (
    <div className="p-4 bg-gray-800 text-white rounded-lg shadow mb-4">
      <h3 className="text-xl font-semibold mb-3 text-blue-400">投资组合摘要</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-gray-400">现金:</p>
          <p className="text-lg font-medium">${formatCurrency(portfolioStatus.cash)}</p>
        </div>
        <div>
          <p className="text-gray-400">持仓市值:</p>
          <p className="text-lg font-medium">${formatCurrency(portfolioStatus.holdings_value)}</p>
        </div>
        <div>
          <p className="text-gray-400">总资产:</p>
          <p className="text-lg font-medium">${formatCurrency(portfolioStatus.total_value)}</p>
        </div>
        <div>
          <p className="text-gray-400">已实现盈亏:</p>
          <p className={`text-lg font-medium ${portfolioStatus.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${formatCurrency(portfolioStatus.realized_pnl)}
          </p>
        </div>
        <div>
          <p className="text-gray-400">未实现盈亏:</p>
          <p className={`text-lg font-medium ${portfolioStatus.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${formatCurrency(portfolioStatus.unrealized_pnl)}
          </p>
        </div>
        <div>
          <p className="text-gray-400">总盈亏:</p>
          <p className={`text-lg font-medium ${portfolioStatus.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${formatCurrency(portfolioStatus.total_pnl)}
          </p>
        </div>
        <div>
          <p className="text-gray-400">模拟运行中:</p>
          <p className={`text-lg font-medium ${displayRunningStatus ? 'text-green-400' : 'text-yellow-400'}`}>
            {displayRunningStatus ? '是' : '否 (已停止)'}
          </p>
        </div>
      </div>
      {Object.keys(portfolioStatus.asset_allocation || {}).length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-700">
          <h4 className="text-md font-semibold mb-2 text-blue-300">资产分配 (% 总净值):</h4>
          <ul className="list-disc list-inside text-sm space-y-1">
            {Object.entries(portfolioStatus.asset_allocation || {}).map(([symbol, percentage]) => (
              <li key={symbol} className="text-gray-300">
                <span className="font-medium text-white">{symbol}:</span> {percentage.toFixed(2)}%
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default PortfolioSummary; 
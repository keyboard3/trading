import React from 'react';
import type { PortfolioStatus } from '../types';

interface PortfolioSummaryProps {
  portfolioStatus?: PortfolioStatus;
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

  return (
    <div className="p-4 bg-gray-800 text-white rounded-lg shadow mb-4">
      <h3 className="text-xl font-semibold mb-3 text-blue-400">投资组合摘要</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-gray-400">现金:</p>
          <p className="text-lg font-medium">${portfolioStatus.cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-gray-400">持仓市值:</p>
          <p className="text-lg font-medium">${portfolioStatus.holdings_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-gray-400">总资产:</p>
          <p className="text-lg font-medium">${portfolioStatus.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
        </div>
        <div>
          <p className="text-gray-400">模拟运行中:</p>
          <p className={`text-lg font-medium ${displayRunningStatus ? 'text-green-400' : 'text-yellow-400'}`}>
            {displayRunningStatus ? '是' : '否 (已停止)'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default PortfolioSummary; 
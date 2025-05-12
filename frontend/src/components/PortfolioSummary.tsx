import React from 'react';
import type { PortfolioStatusResponse } from '../types';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';

interface PortfolioSummaryProps {
  portfolioStatus: PortfolioStatusResponse | null;
  isLoading: boolean;
  error: string | null;
}

const PortfolioSummary: React.FC<PortfolioSummaryProps> = ({ portfolioStatus, isLoading, error }) => {
  const isActuallyRunning = portfolioStatus?.is_running ?? false;

  if (isLoading) {
    return <div className="p-4 bg-gray-700 rounded-lg shadow text-white">投资组合摘要加载中...</div>;
  }

  if (error) {
    return <div className="p-4 bg-red-700 rounded-lg shadow text-white">错误: {error}</div>;
  }

  if (!portfolioStatus) {
    return <div className="p-4 bg-gray-700 rounded-lg shadow text-white">无投资组合数据。</div>;
  }

  const formatCurrency = (value: number) => {
    return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const allocationEntries = Object.entries(portfolioStatus.asset_allocation || {});

  return (
    <Card className="bg-card text-card-foreground">
      <CardHeader>
        <CardTitle className="text-lg">
          投资组合概览 
          <span className={`ml-2 text-xs font-normal px-2 py-0.5 rounded-full ${isActuallyRunning ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
            {isActuallyRunning ? '运行中' : '已停止'}
          </span>
        </CardTitle>
      </CardHeader>
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
      </div>
      {allocationEntries.length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-700">
          <h4 className="text-md font-semibold mb-2 text-gray-600">资产分配 (% 总净值):</h4>
          <ul className="list-disc list-inside text-sm space-y-1">
            {allocationEntries.map(([symbol, percentage]) => (
              <li key={symbol} className="text-gray-700">
                <span className="font-medium text-gray-900">{symbol}:</span> {percentage.toFixed(2)}%
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
};

export default PortfolioSummary; 
import React from 'react';
import type { HoldingStatus } from '../types'; // Type-only import

interface HoldingsTableProps {
  holdings: HoldingStatus[];
  isLoading: boolean;
  error?: string | null; 
}

const HoldingsTable: React.FC<HoldingsTableProps> = ({ holdings, isLoading, error }) => {
  if (isLoading) {
    return <div className="p-4 bg-gray-700 rounded-lg shadow text-white">持仓加载中...</div>;
  }

  if (error) {
    // Error state handled by parent or a more global component, 
    // or display a specific error for this table if appropriate.
    // For now, if an error occurs at a higher level, this component might not even be rendered with data.
    // If it is rendered but holdings array is empty due to an error elsewhere, the 'no holdings' message will show.
    return null; // Or a specific error message for this table if error is passed down directly for it
  }

  if (!holdings || holdings.length === 0) {
    return <div className="p-4 bg-gray-800 text-white rounded-lg shadow text-center">无持仓记录。</div>;
  }

  return (
    <div className="p-4 bg-gray-800 text-white rounded-lg shadow mb-4">
      <h3 className="text-xl font-semibold mb-3 text-blue-400">当前持仓</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-700">
          <thead className="bg-gray-750">
            <tr>
              <th scope="col" className="py-3 px-4 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">代码</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">数量</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">平均成本</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">当前价格</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">市值</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">未实现盈亏</th>
            </tr>
          </thead>
          <tbody className="bg-gray-800 divide-y divide-gray-700">
            {holdings.map((holding) => (
              <tr key={holding.symbol} className="hover:bg-gray-700">
                <td className="py-4 px-4 whitespace-nowrap text-sm font-medium text-blue-300">{holding.symbol}</td>
                <td className="py-4 px-4 whitespace-nowrap text-sm text-right text-gray-300">{holding.quantity.toLocaleString()}</td>
                <td className="py-4 px-4 whitespace-nowrap text-sm text-right text-gray-300">
                  ${holding.average_cost_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="py-4 px-4 whitespace-nowrap text-sm text-right text-gray-300">
                  {holding.current_price != null ? `$${holding.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}` : 'N/A'}
                </td>
                <td className="py-4 px-4 whitespace-nowrap text-sm text-right text-gray-300">
                  {holding.market_value != null ? `$${holding.market_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'N/A'}
                </td>
                <td className={`py-4 px-4 whitespace-nowrap text-sm text-right font-medium ${holding.unrealized_pnl != null && holding.unrealized_pnl > 0 ? 'text-green-400' : holding.unrealized_pnl != null && holding.unrealized_pnl < 0 ? 'text-red-400' : 'text-gray-300'}`}>
                  {holding.unrealized_pnl != null ? `$${holding.unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'N/A'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default HoldingsTable; 
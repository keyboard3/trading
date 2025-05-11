import React from 'react';
import type { ApiTradeRecord } from '../types'; // Type-only import

interface TradesListProps {
  trades: ApiTradeRecord[];
  isLoading: boolean;
  error?: string | null; 
}

const TradesList: React.FC<TradesListProps> = ({ trades, isLoading, error }) => {
  if (isLoading) {
    return <div className="p-4 bg-gray-700 rounded-lg shadow text-white">交易列表加载中...</div>;
  }

  if (error) {
    return null; // Similar to HoldingsTable, parent will handle general error display
  }

  if (!trades || trades.length === 0) {
    return <div className="p-4 bg-gray-800 text-white rounded-lg shadow text-center">无交易记录。</div>;
  }

  return (
    <div className="p-4 bg-gray-800 text-white rounded-lg shadow">
      <h3 className="text-xl font-semibold mb-3 text-blue-400">最近交易</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-700">
          <thead className="bg-gray-750">
            <tr>
              <th scope="col" className="py-3 px-4 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">ID</th>
              <th scope="col" className="py-3 px-4 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">时间</th>
              <th scope="col" className="py-3 px-4 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">代码</th>
              <th scope="col" className="py-3 px-4 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">类型</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">数量</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">价格</th>
              <th scope="col" className="py-3 px-4 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">总价值</th>
            </tr>
          </thead>
          <tbody className="bg-gray-800 divide-y divide-gray-700">
            {trades.slice().reverse().map((trade) => ( // Display newest trades first by reversing a copy
              <tr key={trade.trade_id} className="hover:bg-gray-700">
                <td className="py-3 px-4 whitespace-nowrap text-xs text-gray-400">{trade.trade_id}</td>
                <td className="py-3 px-4 whitespace-nowrap text-sm text-gray-300">{new Date(trade.timestamp * 1000).toLocaleString()}</td>
                <td className="py-3 px-4 whitespace-nowrap text-sm font-medium text-blue-300">{trade.symbol}</td>
                <td className={`py-3 px-4 whitespace-nowrap text-sm font-medium ${trade.type === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                  {trade.type}
                </td>
                <td className="py-3 px-4 whitespace-nowrap text-sm text-right text-gray-300">{trade.quantity.toLocaleString()}</td>
                <td className="py-3 px-4 whitespace-nowrap text-sm text-right text-gray-300">
                  ${trade.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                </td>
                <td className="py-3 px-4 whitespace-nowrap text-sm text-right text-gray-300">
                  ${trade.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TradesList; 
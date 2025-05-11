import React from 'react';
import type { ApiStrategyInfo } from '../types';

interface StrategyInfoDisplayProps {
  strategyInfo?: ApiStrategyInfo | null;
}

const StrategyInfoDisplay: React.FC<StrategyInfoDisplayProps> = ({ strategyInfo }) => {
  if (!strategyInfo) {
    return (
      <div className="p-3 bg-yellow-100 border border-yellow-300 rounded-lg shadow text-sm text-yellow-800">
        当前模拟策略信息不可用。
      </div>
    );
  }

  return (
    <div className="p-4 bg-gray-800 text-white rounded-lg shadow mb-4">
      <h3 className="text-xl font-semibold mb-3 text-blue-400">当前模拟策略</h3>
      <div className="text-sm">
        <p>
          <span className="font-medium text-gray-400">策略名称:</span> 
          <span className="ml-2 text-indigo-300">{strategyInfo.name}</span>
        </p>
        <div className="mt-2">
          <ul className="pl-4 mt-1 space-y-1">
            {Object.entries(strategyInfo.parameters).map(([key, value]) => (
              <li key={key}>
                <span className="text-gray-500">{key}:</span> 
                <span className="ml-1 text-gray-300">{String(value)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

export default StrategyInfoDisplay; 
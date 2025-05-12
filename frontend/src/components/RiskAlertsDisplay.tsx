import React from 'react';
import type { ApiRiskAlert } from '../types';

interface RiskAlertsDisplayProps {
  alerts?: ApiRiskAlert[] | null;
}

const RiskAlertsDisplay: React.FC<RiskAlertsDisplayProps> = ({ alerts }) => {
  if (!alerts || alerts.length === 0) {
    return (
      <div className="p-3 bg-gray-700 rounded-lg shadow text-sm text-gray-300">
        无风险告警。
      </div>
    );
  }

  const formatAlertType = (alertType: string): string => {
    // Simple mapping for now, can be expanded
    const typeMap: Record<string, string> = {
      'STOP_LOSS_PER_POSITION': '个股止损',
      'MAX_POSITION_SIZE': '最大持仓规模 (个股)',
      'MAX_POSITION_SIZE_PRE_TRADE': '预交易-最大持仓规模 (个股)',
      'MAX_ACCOUNT_DRAWDOWN': '账户最大回撤',
    };
    return typeMap[alertType] || alertType.replace(/_/g, ' '); // Fallback to space-separated type
  };

  return (
    <div className="p-4 bg-red-800 border border-red-700 rounded-lg shadow text-white">
      <h4 className="text-md font-semibold mb-2 text-yellow-300">风险告警</h4>
      <ul className="space-y-2 text-xs">
        {alerts.map((alert, index) => (
          <li key={index} className="p-2 bg-red-700 rounded">
            <div className="font-medium text-yellow-400">
              类型: {formatAlertType(alert.alert_type)}
              {alert.symbol && <span className="ml-2">(代码: {alert.symbol})</span>}
            </div>
            <p className="text-red-200 mt-1">消息: {alert.message}</p>
            <p className="text-xs text-red-300 mt-1">
              时间: {new Date(alert.timestamp * 1000).toLocaleString()}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default RiskAlertsDisplay; 
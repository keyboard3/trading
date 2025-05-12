import React from 'react';
import type { ApiRiskAlert } from '../types';

interface RiskAlertsDisplayProps {
  alerts?: ApiRiskAlert[] | null;
}

const RiskAlertsDisplay: React.FC<RiskAlertsDisplayProps> = ({ alerts }) => {
  if (!alerts || alerts.length === 0) {
    return (
      <div className="p-4 bg-gray-800 text-white rounded-lg shadow mb-4">
        <h3 className="text-xl font-semibold mb-2 text-blue-400">风险告警</h3>
        <p className="text-sm text-gray-400">当前无风险告警。</p>
      </div>
    );
  }

  const getAlertColor = (alertType: string) => {
    if (alertType.includes('STOP_LOSS')) return 'text-red-400';
    if (alertType.includes('DRAWDOWN')) return 'text-red-500';
    if (alertType.includes('MAX_POSITION')) return 'text-yellow-400';
    return 'text-gray-300'; // Default color for unknown types
  };

  return (
    <div className="p-4 bg-gray-800 text-white rounded-lg shadow mb-4">
      <h3 className="text-xl font-semibold mb-3 text-blue-400">风险告警</h3>
      <div className="space-y-3 max-h-60 overflow-y-auto pr-2"> {/* Added max height and scroll */} 
        {alerts.map((alert, index) => (
          <div key={index} className={`p-3 rounded-md bg-gray-700 shadow-sm border-l-4 ${getAlertColor(alert.alert_type).replace('text-', 'border-')}`}>
            <div className="flex justify-between items-center mb-1">
              <span className={`font-semibold ${getAlertColor(alert.alert_type)}`}>
                {alert.alert_type}
                {alert.symbol && <span className="ml-2 font-normal text-gray-400">({alert.symbol})</span>}
              </span>
              <span className="text-xs text-gray-500">{new Date(alert.timestamp * 1000).toLocaleString()}</span>
            </div>
            <p className="text-sm text-gray-300">{alert.message}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default RiskAlertsDisplay; 
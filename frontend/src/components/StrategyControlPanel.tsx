import React, { useState, useEffect, useCallback } from 'react';
import { fetchAvailableStrategies, startSimulation, stopSimulation } from '../api';
import type { AvailableStrategy, StrategyParameterSpec, StartSimulationRequest } from '../types';

interface StrategyControlPanelProps {
  onSimulationAction: () => void; // Callback after start/stop/resume action
  isRunning: boolean; // Current simulation running state
  isResumable: boolean; // Indicates if a resumable state exists
  currentStrategyName?: string | null; // Optional: Name of current strategy if running/resumed
}

const StrategyControlPanel: React.FC<StrategyControlPanelProps> = ({ 
  onSimulationAction,
  isRunning,
  isResumable,
  currentStrategyName
}) => {
  const [availableStrategies, setAvailableStrategies] = useState<AvailableStrategy[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('');
  const [parameters, setParameters] = useState<Record<string, any>>({});
  const [initialCapitalBaseUnit, setInitialCapitalBaseUnit] = useState<string>('100000');
  const [initialCapitalDisplayWan, setInitialCapitalDisplayWan] = useState<string>(
    String(parseFloat('100000') / 10000)
  );
  const [isLoadingStrategies, setIsLoadingStrategies] = useState<boolean>(false);
  const [isLoadingAction, setIsLoadingAction] = useState<boolean>(false); // For start/stop actions
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null); // For success/info messages from start/stop

  // Data Provider States
  const [dataProviderType, setDataProviderType] = useState<'mock' | 'yahoo'>('mock');
  const [yahooPollingInterval, setYahooPollingInterval] = useState<string>('60'); // Default 60 seconds, as string for input

  // Risk Parameters States (User inputs percentages, e.g., 10 for 10%)
  const [stopLossPct, setStopLossPct] = useState<string>('10'); // Default 10%
  const [maxPositionPct, setMaxPositionPct] = useState<string>('25'); // Default 25%
  const [accountMaxDrawdownPct, setAccountMaxDrawdownPct] = useState<string>('15'); // Default 15%

  useEffect(() => {
    const loadStrategies = async () => {
      setIsLoadingStrategies(true);
      setError(null);
      try {
        const strategies = await fetchAvailableStrategies();
        setAvailableStrategies(strategies);
        if (strategies.length > 0) {
          // Optionally pre-select the first one and its default params
          // setSelectedStrategyId(strategies[0].id); 
        }
      } catch (err) {
        setError(err instanceof Error ? `获取可用策略失败: ${err.message}` : String(err));
      }
      setIsLoadingStrategies(false);
    };
    loadStrategies();
  }, []);

  const selectedStrategyDetails = availableStrategies.find(s => s.id === selectedStrategyId);

  const handleParameterChange = (paramName: string, value: string, type: StrategyParameterSpec['type']) => {
    let processedValue: any = value;
    if (type === 'int') {
      // Allow empty string for easier clearing of input, parse when needed or on submit
      if (value === '') {
        processedValue = ''; 
      } else {
        const num = parseInt(value, 10);
        processedValue = isNaN(num) ? parameters[paramName] : num; // Revert if NaN, or keep empty if user intended
      }
    } else if (type === 'float') {
      if (value === '') {
        processedValue = '';
      } else {
        const num = parseFloat(value);
        processedValue = isNaN(num) ? parameters[paramName] : num;
      }
    }
    setParameters(prev => ({ ...prev, [paramName]: processedValue }));
  };

  useEffect(() => {
    if (selectedStrategyDetails) {
      const defaultParams: Record<string, any> = {};
      selectedStrategyDetails.parameters.forEach(param => {
        if (param.default !== undefined) {
          defaultParams[param.name] = param.default;
        } else {
          // For types that might be numeric, empty string is often better for controlled inputs than 0
          defaultParams[param.name] = ''; 
        }
      });
      setParameters(defaultParams);
      setError(null); // Clear previous errors when strategy changes
      setActionMessage(null); // Clear previous messages
    } else {
      setParameters({}); // Clear params if no strategy is selected
    }
  }, [selectedStrategyDetails]);

  const handleStartSimulation = async () => {
    if (!selectedStrategyId) {
      setError('请先选择一个策略。');
      return;
    }
    // Validate initial capital using the base unit
    const capitalBase = parseFloat(initialCapitalBaseUnit);
    if (isNaN(capitalBase) || capitalBase <= 0) {
      setError('初始资金必须是一个正数。');
      return;
    }

    // --- Validate and prepare risk parameters ---
    const riskParams: Record<string, number> = {};
    const slPct = parseFloat(stopLossPct);
    const mpPct = parseFloat(maxPositionPct);
    const amdPct = parseFloat(accountMaxDrawdownPct);
    let riskValidationError = false;

    if (!isNaN(slPct) && slPct > 0) {
      riskParams['stop_loss_pct'] = slPct / 100;
    } else if (stopLossPct !== '') { // Allow empty if user wants to use backend default
      setError('个股止损百分比必须是正数，或留空以使用默认值。');
      riskValidationError = true;
    }

    if (!isNaN(mpPct) && mpPct > 0 && mpPct <= 100) {
      riskParams['max_pos_pct'] = mpPct / 100;
    } else if (maxPositionPct !== '') {
      setError('单资产最大持仓百分比必须是0到100之间的正数，或留空。');
      riskValidationError = true;
    }

    if (!isNaN(amdPct) && amdPct > 0 && amdPct <= 100) {
      riskParams['max_dd_pct'] = amdPct / 100;
    } else if (accountMaxDrawdownPct !== '') {
      setError('账户最大回撤百分比必须是0到100之间的正数，或留空。');
      riskValidationError = true;
    }

    if (riskValidationError) {
      setIsLoadingAction(false);
      return;
    }
    // --- End of Risk Parameters Validation ---

    // --- Validate Yahoo Polling Interval if applicable ---
    let pollingIntervalNum: number | undefined = undefined;
    if (dataProviderType === 'yahoo') {
      pollingIntervalNum = parseInt(yahooPollingInterval, 10);
      if (isNaN(pollingIntervalNum) || pollingIntervalNum <= 0) {
        setError('Yahoo Finance 数据轮询间隔必须是一个正整数（秒）。');
        setIsLoadingAction(false);
        return;
      }
    }
    // --- End of Yahoo Polling Interval Validation ---

    setIsLoadingAction(true);
    setError(null);
    setActionMessage(null);
    try {
      // Validate and convert parameters before sending
      const finalParameters: Record<string, any> = {};
      let validationError = false;
      selectedStrategyDetails?.parameters.forEach(paramSpec => {
        let value = parameters[paramSpec.name];
        if (paramSpec.type === 'int') {
          value = parseInt(value, 10);
          if (isNaN(value) && paramSpec.required) validationError = true;
        } else if (paramSpec.type === 'float') {
          value = parseFloat(value);
          if (isNaN(value) && paramSpec.required) validationError = true;
        }
        if (paramSpec.required && (value === '' || value === undefined || (typeof value === 'number' && isNaN(value)))) {
            validationError = true;
            setError(`参数 '${paramSpec.name}' 是必需的且不能为空或无效值。`);
        }
        finalParameters[paramSpec.name] = value;
      });

      if (validationError) {
        setIsLoadingAction(false);
        if (!error) setError("一个或多个参数无效或缺失。"); // Generic if specific not set
        return;
      }

      const payload: StartSimulationRequest = {
        strategy_id: selectedStrategyId,
        parameters: finalParameters,
        initial_capital: capitalBase, // Send base unit to payload
        risk_parameters: Object.keys(riskParams).length > 0 ? riskParams : undefined, // Add risk_parameters, send undefined if empty
        data_provider_type: dataProviderType, // Add data provider type
      };
      
      if (dataProviderType === 'yahoo' && pollingIntervalNum !== undefined) {
        payload.yahoo_polling_interval = pollingIntervalNum; // Add polling interval if yahoo
      }

      const response = await startSimulation(payload);
      setActionMessage(response.message || '模拟已成功启动。');
    } catch (err) {
      setError(err instanceof Error ? `启动模拟失败: ${err.message}` : String(err));
    }
    setIsLoadingAction(false);
  };

  const handleStopSimulation = async () => {
    setIsLoadingAction(true);
    setError(null);
    setActionMessage(null);
    try {
      const response = await stopSimulation();
      setActionMessage(response.message || '模拟已成功停止。');
    } catch (err) {
      setError(err instanceof Error ? `停止模拟失败: ${err.message}` : String(err));
    }
    setIsLoadingAction(false);
  };

  const handleInitialCapitalDisplayChange = (displayValueWan: string) => {
    setInitialCapitalDisplayWan(displayValueWan);
    if (displayValueWan === '') {
      setInitialCapitalBaseUnit('');
    } else {
      const numWan = parseFloat(displayValueWan);
      if (!isNaN(numWan)) {
        setInitialCapitalBaseUnit(String(numWan * 10000));
      } else {
        // If input is not a valid number (e.g., "abc"), clear base unit or handle as error
        // For now, clearing base unit will trigger validation on submit
        setInitialCapitalBaseUnit(''); 
      }
    }
  };

  return (
    <div className="strategy-control-panel">
      <h4>策略控制面板</h4>
      {isLoadingStrategies && <p className="text-xs text-gray-400 my-1">正在加载可用策略...</p>}
      {error && <p className="text-xs text-red-500 my-1">错误: {error}</p>}
      {actionMessage && <p className="text-xs text-green-500 my-1">{actionMessage}</p>}

      <div className="form-group flex flex-row items-center">
        <label htmlFor="strategy-select" className='mr-2'>选择策略:</label>
        <select 
          id="strategy-select"
          value={selectedStrategyId}
          className='flex-1 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50'
          onChange={e => setSelectedStrategyId(e.target.value)}
          disabled={isLoadingStrategies || isRunning}
        >
          <option value="" disabled={selectedStrategyId !== ''}>-- 请选择 --</option>
          {availableStrategies.map(strategy => (
            <option key={strategy.id} value={strategy.id}>{strategy.name}</option>
          ))}
        </select>
      </div>

      {/* --- Data Provider Selection --- */}
      <div className="form-group flex flex-row items-center mt-2">
        <label htmlFor="data-provider-select" className='mr-2'>数据源:</label>
        <select
          id="data-provider-select"
          value={dataProviderType}
          className='flex-1 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50'
          onChange={e => setDataProviderType(e.target.value as 'mock' | 'yahoo')}
          disabled={isRunning || isLoadingAction}
        >
          <option value="mock">内部模拟数据</option>
          <option value="yahoo">Yahoo Finance (延迟)</option>
        </select>
      </div>

      {dataProviderType === 'yahoo' && (
        <div className="form-group flex flex-row items-center mt-1 ml-4"> {/* Indent slightly */}
          <label htmlFor="yahoo-interval-input" className='mr-2 text-sm text-gray-400'>轮询间隔 (秒):</label>
          <input
            id="yahoo-interval-input"
            type="number"
            value={yahooPollingInterval}
            onChange={e => setYahooPollingInterval(e.target.value)}
            className='flex-1 text-sm bg-gray-800 border border-gray-600 rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50'
            placeholder="例如: 60"
            min="1"
            step="1"
            disabled={isRunning || isLoadingAction}
          />
        </div>
      )}
      {/* --- End Data Provider Selection --- */}

      {selectedStrategyDetails && (
        <div className="strategy-parameters">
          <h5 className="mt-2 mb-1">策略: {selectedStrategyDetails.name}</h5>
          <p className="text-sm text-gray-400 mb-2">{selectedStrategyDetails.description}</p>
          <h6 className="mb-1">参数:</h6>
          {selectedStrategyDetails.parameters.map(param => (
            <div key={param.name} className="form-group param-row"> 
              <div className="param-label-container">
                <label htmlFor={`param-${param.name}`}>
                  {param.name}{param.required ? '*' : ''}:
                </label>
              </div>
              <div className="param-input-container">
                <input
                  type={param.type === 'int' || param.type === 'float' ? 'number' : 'text'}
                  id={`param-${param.name}`}
                  value={parameters[param.name] === undefined ? '' : parameters[param.name]}
                  onChange={e => handleParameterChange(param.name, e.target.value, param.type)}
                  disabled={isRunning}
                  className="w-full disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
              <div className="param-description-container">
                {param.description && <small>{param.description}</small>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Initial Capital Input */}
      {selectedStrategyId && ( // Only show if a strategy is selected
        <div className="form-group param-row mt-3">
          <div className="param-label-container">
            <label htmlFor="initial-capital">初始资金 (万元):</label>
          </div>
          <div className="param-input-container">
            <input
              type="number"
              id="initial-capital"
              value={initialCapitalDisplayWan}
              onChange={e => handleInitialCapitalDisplayChange(e.target.value)}
              disabled={isRunning}
              className="w-full disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="例如: 10"
            />
          </div>
          <div className="param-description-container">
            <small>模拟开始时的账户现金 (万元)</small>
          </div>
        </div>
      )}

      {/* --- Risk Parameters Section --- */}
      {selectedStrategyId && ( // Only show if a strategy is selected
        <div className="risk-parameters-section mt-3 border-t pt-3">
          <h6 className="mb-2 font-semibold text-sm">风险参数配置:</h6>
          
          {/* Stop Loss Percentage */}
          <div className="form-group param-row">
            <div className="param-label-container">
              <label htmlFor="stop-loss-pct">个股止损 (%):</label>
            </div>
            <div className="param-input-container">
              <input
                type="number"
                id="stop-loss-pct"
                value={stopLossPct}
                onChange={e => setStopLossPct(e.target.value)}
                disabled={isRunning}
                className="w-full disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="例如: 10 (表示10%)"
              />
            </div>
            <div className="param-description-container">
              <small>单笔持仓最大亏损容忍度。</small>
            </div>
          </div>

          {/* Max Position Percentage */}
          <div className="form-group param-row mt-2">
            <div className="param-label-container">
              <label htmlFor="max-position-pct">单资产最大持仓 (%):</label>
            </div>
            <div className="param-input-container">
              <input
                type="number"
                id="max-position-pct"
                value={maxPositionPct}
                onChange={e => setMaxPositionPct(e.target.value)}
                disabled={isRunning}
                className="w-full disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="例如: 25 (表示25%)"
              />
            </div>
            <div className="param-description-container">
              <small>单一资产市值占总资产最大比例。</small>
            </div>
          </div>

          {/* Account Max Drawdown Percentage */}
          <div className="form-group param-row mt-2">
            <div className="param-label-container">
              <label htmlFor="account-max-drawdown-pct">账户最大回撤 (%):</label>
            </div>
            <div className="param-input-container">
              <input
                type="number"
                id="account-max-drawdown-pct"
                value={accountMaxDrawdownPct}
                onChange={e => setAccountMaxDrawdownPct(e.target.value)}
                disabled={isRunning}
                className="w-full disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="例如: 15 (表示15%)"
              />
            </div>
            <div className="param-description-container">
              <small>账户总净值从峰值最大回落容忍度。</small>
            </div>
          </div>
        </div>
      )}

      <div className="simulation-controls mt-4 space-x-2">
        <button 
          onClick={handleStartSimulation} 
          disabled={isLoadingAction || isRunning || !selectedStrategyId}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-500 disabled:cursor-not-allowed"
        >
          启动模拟
        </button>
        <button 
          onClick={handleStopSimulation} 
          disabled={isLoadingAction || !isRunning}
          className="disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoadingAction && isRunning ? '正在停止...' : '停止模拟'}
        </button>
      </div>
      {isRunning && currentStrategyName && (
         <p className="text-xs text-gray-400 italic mt-2">当前运行的策略: {currentStrategyName}</p>
      )}
    </div>
  );
};

export default StrategyControlPanel; 
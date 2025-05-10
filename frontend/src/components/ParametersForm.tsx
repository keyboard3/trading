import React, { useState, useEffect } from 'react';
import type { Strategy } from './StrategySelector'; // 复用Strategy类型

interface ParametersFormProps {
  strategy: Strategy | null; // 当前选中的策略
  onParametersChange: (params: Record<string, any>) => void; 
}

const ParametersForm: React.FC<ParametersFormProps> = ({ strategy, onParametersChange }) => {
  const [currentParams, setCurrentParams] = useState<Record<string, any>>({});

  useEffect(() => {
    if (strategy && strategy.default_params) {
      setCurrentParams(strategy.default_params);
      onParametersChange(strategy.default_params); 
    } else {
      setCurrentParams({});
      onParametersChange({});
    }
  }, [strategy, onParametersChange]);

  const handleInputChange = (paramName: string, value: string | number | boolean) => {
    const newParamValue = isNaN(Number(value)) ? value : Number(value); 

    const updatedParams = {
      ...currentParams,
      [paramName]: newParamValue,
    };
    setCurrentParams(updatedParams);
    onParametersChange(updatedParams); 
  };

  if (!strategy) {
    return <p className="text-sm text-gray-500">请先选择一个策略以配置参数。</p>;
  }

  return (
    <div className="mt-6 border-t pt-4">
      <h3 className="text-md font-semibold text-gray-800 mb-2">策略参数配置:</h3>
      {Object.keys(strategy.default_params).length === 0 && (
        <p className="text-sm text-gray-500">此策略没有可配置的参数。</p>
      )}
      {Object.keys(strategy.default_params).map((paramName) => {
        const defaultValue = strategy.default_params[paramName];
        const inputType = typeof defaultValue === 'number' ? 'number' : 'text';

        return (
          <div key={paramName} className="mb-3">
            <label htmlFor={`param-${paramName}`} className="block text-sm font-medium text-gray-700 capitalize">
              {paramName.replace(/_/g, ' ')}: 
            </label>
            <input
              type={inputType}
              id={`param-${paramName}`}
              name={paramName}
              value={currentParams[paramName] !== undefined ? String(currentParams[paramName]) : ''}
              onChange={(e) => handleInputChange(paramName, e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            />
          </div>
        );
      })}
    </div>
  );
};

export default ParametersForm; 
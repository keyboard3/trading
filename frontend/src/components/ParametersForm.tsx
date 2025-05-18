import React, { useState, useEffect } from 'react';
import type { Strategy } from './StrategySelector'; // 复用Strategy类型

interface ParametersFormProps {
  strategy: Strategy | null; // 当前选中的策略
  onParametersChange: (params: Record<string, any>) => void; 
}

const ParametersForm: React.FC<ParametersFormProps> = ({ strategy, onParametersChange }) => {
  const [currentParams, setCurrentParams] = useState<Record<string, any>>({});

  useEffect(() => {
    // 当策略改变时，用策略的默认参数重置表单，并通知父组件
    const initialParams = strategy?.default_params || {};
    setCurrentParams(initialParams);
    onParametersChange(initialParams); 
  }, [strategy, onParametersChange]);

  const handleInputChange = (paramName: string, value: string | number | boolean) => {
    // 尝试将输入值转换为数字，如果参数的默认值是数字类型的话
    const defaultValue = strategy?.default_params?.[paramName];
    const newParamValue = typeof defaultValue === 'number' && !isNaN(Number(value)) 
                          ? Number(value) 
                          : value;

    const updatedParams = {
      ...currentParams,
      [paramName]: newParamValue,
    };
    setCurrentParams(updatedParams);
    onParametersChange(updatedParams); 
  };

  if (!strategy) {
    return <p className="text-sm text-gray-500 mt-4">请先选择一个策略以配置参数。</p>;
  }

  const strategyParams = strategy.default_params || {};
  const paramKeys = Object.keys(strategyParams);

  if (paramKeys.length === 0) {
    return <p className="text-sm text-gray-500 mt-4">此策略没有可配置的参数。</p>;
  }

  return (
    <div className="mt-6 border-t border-gray-200 pt-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">策略参数配置:</h3>
      <div className="flex flex-col gap-4">
        {paramKeys.map((paramName) => {
          const paramConfig = strategy.parameters?.[paramName];
          const defaultValue = strategyParams[paramName];
          
          let inputType = 'text';
          if (typeof defaultValue === 'number') inputType = 'number';

          // 使用策略定义中的 label_cn，如果不存在则回退
          const displayLabel = paramConfig?.label_cn || paramName.replace(/_/g, ' ').split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');

          return (
            <div key={paramName} className="flex flex-row items-center gap-2">
              <label 
                htmlFor={`param-${paramName}`} 
                className="w-1/3 flex-shrink-0 block text-sm font-medium text-gray-700 md:w-2/5 lg:w-1/3"
              >
                {displayLabel}
              </label>
              <input
                type={inputType}
                id={`param-${paramName}`}
                name={paramName}
                value={currentParams[paramName] !== undefined ? String(currentParams[paramName]) : ''}
                onChange={(e) => handleInputChange(paramName, e.target.value)}
                className="block w-full flex-grow px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ParametersForm; 
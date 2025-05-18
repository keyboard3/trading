import React, { useState, useEffect } from 'react';

// 预期的单个策略对象结构
export interface StrategyParameter { // Representing a single parameter's config
  type: string;
  default: any;
  min?: number;
  max?: number;
  step?: number;
  label_cn: string;
  options?: { label: string; value: any }[]; // For select/radio types if you add them later
}

export interface Strategy {
  id: string;
  name: string; // Display Name
  description?: string;
  parameters: Record<string, StrategyParameter>; // Full parameter definitions from API
  default_params: Record<string, any>; // Extracted default values { paramName: defaultValue }
  // param_grid?: Record<string, any[]>; // If you use this later
}

// StrategySelector 组件的 Props
export interface StrategySelectorProps {
  selectedStrategyId: string | null;
  onStrategySelect: (strategy: Strategy | null) => void;
}

const StrategySelector: React.FC<StrategySelectorProps> = ({ selectedStrategyId, onStrategySelect }) => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStrategies = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/v1/strategies');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const apiResponseData: Record<string, any> = await response.json();
        console.log('Raw data from API:', apiResponseData);

        // const knownMetadataKeys = ['module_name', 'function_name', 'param_grid', 'indicator_cols', 'display_name', 'description']; // Not needed for default_params extraction

        const transformedStrategies: Strategy[] = Object.keys(apiResponseData).map(id => {
          const apiConfig = apiResponseData[id]; // This is the strategy object from the API
          
          const defaultParams: Record<string, any> = {};
          const strategySpecificParameters: Record<string, StrategyParameter> = {};

          if (apiConfig.parameters && typeof apiConfig.parameters === 'object') {
            for (const paramName in apiConfig.parameters) {
              if (Object.prototype.hasOwnProperty.call(apiConfig.parameters, paramName)) {
                const paramConfig = apiConfig.parameters[paramName];
                if (paramConfig && typeof paramConfig === 'object' && 'default' in paramConfig) {
                  defaultParams[paramName] = paramConfig.default;
                  strategySpecificParameters[paramName] = paramConfig as StrategyParameter;
                } else {
                  // Handle cases where a parameter might not have a default, or structure is unexpected
                  console.warn(`Parameter ${paramName} for strategy ${id} has no default value or unexpected structure.`);
                  // defaultParams[paramName] = ''; // Or some other fallback
                  // If paramConfig exists but no default, still add to strategySpecificParameters
                  if (paramConfig && typeof paramConfig === 'object') {
                    strategySpecificParameters[paramName] = paramConfig as StrategyParameter;
                  }
                }
              }
            }
          }

          return {
            id: id, // This is the internal strategy name, e.g., "BYDTrendFollowingStrategy"
            name: apiConfig.display_name || id, // This is the display name
            description: apiConfig.description || `策略 ${id}`,
            default_params: defaultParams, // Now correctly populated
            parameters: strategySpecificParameters, // This will be used by ParametersForm
            // param_grid: apiConfig.param_grid || {} // param_grid is not in your API response from earlier
          };
        });
        
        console.log('Transformed strategies for frontend:', transformedStrategies);
        setStrategies(transformedStrategies);
      } catch (e) {
        if (e instanceof Error) {
          setError(`获取策略失败: ${e.message}`);
        } else {
          setError('获取策略失败，发生未知错误');
        }
        console.error("Error fetching strategies:", e);
      } finally {
        setIsLoading(false);
      }
    };

    fetchStrategies();
  }, []); // 空依赖数组，表示仅在组件挂载时执行一次

  const handleSelectChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const strategyId = event.target.value;
    if (strategyId === "") {
      onStrategySelect(null);
    } else {
      const selected = strategies.find(s => s.id === strategyId);
      onStrategySelect(selected || null);
    }
  };

  if (isLoading) {
    return <p className="text-gray-700">正在加载策略列表...</p>;
  }

  if (error) {
    return <p className="text-red-500">错误: {error}</p>;
  }

  return (
    <div className="mb-4">
      <label htmlFor="strategy-select" className="block text-sm font-medium text-gray-700 mb-1">
        选择交易策略:
      </label>
      <select
        id="strategy-select"
        name="strategy"
        value={selectedStrategyId || ""}
        onChange={handleSelectChange}
        className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md shadow-sm"
      >
        <option value="">-- 请选择一个策略 --</option>
        {strategies.map((strategy) => (
          <option key={strategy.id} value={strategy.id}>
            {strategy.name}
          </option>
        ))}
      </select>
    </div>
  );
};

export default StrategySelector; 
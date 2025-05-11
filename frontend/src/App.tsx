import { useState, useEffect, useCallback } from 'react'
import './App.css'
import Layout from './components/Layout'
// Backtest specific imports
import StrategySelector from './components/StrategySelector'
import type { Strategy } from './components/StrategySelector'
import ParametersForm from './components/ParametersForm'
import StockInput from './components/StockInput'
import DateRangePicker from './components/DateRangePicker'
import RunBacktestButton from './components/RunBacktestButton'
import type { BacktestResponse } from './components/RunBacktestButton'
import ResultsDisplay from './components/ResultsDisplay'

// Simulation specific imports
import SimulationDisplay from './components/SimulationDisplay'
import StrategyControlPanel from './components/StrategyControlPanel' // Import StrategyControlPanel
import type { SimulationStatusResponse } from './types' // Assuming SimulationStatusResponse is in types.ts

// Helper function to format date as YYYY-MM-DD
const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${year}-${month}-${day}`;
};

function App() {
  // --- Backtest States ---
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [strategyParameters, setStrategyParameters] = useState<Record<string, any>>({})
  const [stockSymbolsInput, setStockSymbolsInput] = useState<string>("MSFT")
  const today = new Date()
  const oneYearAgo = new Date(new Date().setFullYear(today.getFullYear() - 1))
  const [startDate, setStartDate] = useState<string>(formatDate(oneYearAgo))
  const [endDate, setEndDate] = useState<string>(formatDate(today))
  const [slippagePctInput, setSlippagePctInput] = useState<string>("0.0001")
  const [backtestApiResponse, setBacktestApiResponse] = useState<BacktestResponse | null>(null)
  const [backtestApiError, setBacktestApiError] = useState<string | null>(null)

  // --- Tab and Simulation Shared States ---
  const [activeTab, setActiveTab] = useState<'backtest' | 'simulation'>('simulation');
  const [isSimulationRunningForControlPanel, setIsSimulationRunningForControlPanel] = useState<boolean>(false);
  const [currentStrategyNameForControlPanel, setCurrentStrategyNameForControlPanel] = useState<string | null>(null);
  const [refreshSimDisplayKey, setRefreshSimDisplayKey] = useState<number>(0);

  // --- Callbacks for Backtest Form ---
  const handleStrategyChange = useCallback((strategy: Strategy | null) => {
    setSelectedStrategy(strategy)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
    if (strategy && strategy.default_params) {
      setStrategyParameters(strategy.default_params)
    } else {
      setStrategyParameters({})
    }
  }, [])

  const handleParametersChange = useCallback((updatedParams: Record<string, any>) => {
    setStrategyParameters(updatedParams)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
  }, [])

  const handleStockSymbolsChange = useCallback((symbols: string) => {
    setStockSymbolsInput(symbols)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
  }, [])

  const handleStartDateChange = useCallback((date: string) => {
    setStartDate(date)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
    setEndDate(prevEndDate => {
      if (new Date(date) > new Date(prevEndDate)) return date;
      return prevEndDate;
    })
  }, [])

  const handleEndDateChange = useCallback((date: string) => {
    setEndDate(date)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
  }, [])

  const handleSlippagePctChange = useCallback((value: string) => {
    setSlippagePctInput(value)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
  }, [])

  const handleBacktestCompletion = useCallback((response: BacktestResponse | null, error?: string) => {
    if (error) {
      setBacktestApiError(error)
      setBacktestApiResponse(null)
    } else if (response) {
      setBacktestApiResponse(response)
      setBacktestApiError(null)
    }
    setActiveTab('backtest');
  }, [])

  // --- Callbacks for Simulation Components ---
  const handleSimulationDataUpdate = useCallback((data: SimulationStatusResponse | null) => {
    setIsSimulationRunningForControlPanel(data?.is_simulation_running || false);
    setCurrentStrategyNameForControlPanel(data?.active_strategy?.name || null);
  }, []);

  const handleStrategyActionTrigger = useCallback(() => {
    setRefreshSimDisplayKey(prevKey => prevKey + 1); // Increment key to trigger refresh
  }, []);

  return (
    <Layout>
      <div className="flex flex-row flex-wrap md:flex-nowrap gap-6">
        {/* Left Panel: Conditional based on activeTab */}
        <div className="w-full md:w-2/5 lg:w-1/3 flex flex-col gap-4 order-2 md:order-1 bg-white p-6 rounded-lg shadow-lg">
          {activeTab === 'backtest' && (
            <>
              <StrategySelector 
                selectedStrategyId={selectedStrategy?.id || null} 
                onStrategySelect={handleStrategyChange} 
              />
              <StockInput 
                stockSymbols={stockSymbolsInput}
                onStockSymbolsChange={handleStockSymbolsChange}
              />
              <DateRangePicker
                startDate={startDate}
                endDate={endDate}
                onStartDateChange={handleStartDateChange}
                onEndDateChange={handleEndDateChange}
              />
              <div className="mt-4">
                <label htmlFor="slippage-pct-input" className="block text-sm font-medium text-gray-700">
                  滑点百分比 (例如 0.0001 表示 0.01%):
                </label>
                <input
                  type="number"
                  id="slippage-pct-input"
                  name="slippagePct"
                  value={slippagePctInput}
                  onChange={(e) => handleSlippagePctChange(e.target.value)}
                  placeholder="例如: 0.0001"
                  step="0.00001"
                  min="0"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                />
              </div>
              <div className="my-2 p-3 bg-gray-50 rounded text-xs space-y-1">
                <div><span className="font-semibold">日期范围:</span> {startDate} 至 {endDate}</div>
                {stockSymbolsInput && <div><span className="font-semibold">当前代码:</span> {stockSymbolsInput}</div>}
              </div>
              {selectedStrategy && (
                <div className="p-3 bg-indigo-50 rounded border border-indigo-200">
                  <h3 className="text-md font-semibold text-indigo-800">当前选中策略:</h3>
                  <p className="text-sm text-gray-700">ID: {selectedStrategy.id}</p>
                  <p className="text-sm text-gray-700">名称: {selectedStrategy.name}</p>
                </div>
              )}
              <ParametersForm 
                strategy={selectedStrategy} 
                onParametersChange={handleParametersChange} 
              />
              <RunBacktestButton
                strategyId={selectedStrategy?.id || null}
                stockSymbols={stockSymbolsInput}
                startDate={startDate}
                endDate={endDate}
                parameters={strategyParameters}
                slippagePct={parseFloat(slippagePctInput) || 0}
                onBacktestComplete={handleBacktestCompletion}
              />
            </>
          )}

          {activeTab === 'simulation' && (
            <StrategyControlPanel 
              onSimulationStatusChange={handleStrategyActionTrigger} // Renamed from onSimulationStatusChange for clarity
              isSimulationRunningCurrently={isSimulationRunningForControlPanel}
              currentStrategyName={currentStrategyNameForControlPanel}
            />
          )}
        </div>

        {/* Right Panel: Results Area */}
        <div className="w-full md:w-3/5 lg:w-2/3 order-1 md:order-2 flex-grow space-y-6">
          {/* Tab Buttons */}
          <div className="mb-4 border-b border-gray-200 dark:border-gray-700">
            <nav className="-mb-px flex space-x-8" aria-label="Tabs">
              <button
                onClick={() => setActiveTab('backtest')}
                className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm 
                            ${activeTab === 'backtest' 
                              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400' 
                              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-500'}`}
              >
                历史回测结果
              </button>
              <button
                onClick={() => setActiveTab('simulation')}
                className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm 
                            ${activeTab === 'simulation' 
                              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400' 
                              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-500'}`}
              >
                实时模拟交易
              </button>
            </nav>
          </div>

          {/* Conditional Rendering based on activeTab */}
          {activeTab === 'backtest' && (
            <ResultsDisplay response={backtestApiResponse} error={backtestApiError} />
          )}

          {activeTab === 'simulation' && (
            <SimulationDisplay 
              key={refreshSimDisplayKey} // Use key to force re-render/refresh if needed
              onDataRefreshed={handleSimulationDataUpdate} // Prop for SimulationDisplay to pass data up
            />
          )}
        </div>
      </div>
    </Layout>
  )
}

export default App;

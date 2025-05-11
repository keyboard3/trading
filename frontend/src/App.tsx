import { useState, useEffect, useCallback } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'
import Layout from './components/Layout'
import StrategySelector from './components/StrategySelector'
import type { Strategy } from './components/StrategySelector'
import ParametersForm from './components/ParametersForm'
import StockInput from './components/StockInput'
import DateRangePicker from './components/DateRangePicker'
import RunBacktestButton from './components/RunBacktestButton'
import type { BacktestResponse } from './components/RunBacktestButton'
import ResultsDisplay from './components/ResultsDisplay'

// Helper function to format date as YYYY-MM-DD
const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${year}-${month}-${day}`;
};

function App() {
  const [count, setCount] = useState(0)
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [strategyParameters, setStrategyParameters] = useState<Record<string, any>>({})
  const [stockSymbolsInput, setStockSymbolsInput] = useState<string>("MSFT")
  
  const today = new Date()
  const oneYearAgo = new Date(new Date().setFullYear(today.getFullYear() - 1))
  const [startDate, setStartDate] = useState<string>(formatDate(oneYearAgo))
  const [endDate, setEndDate] = useState<string>(formatDate(today))
  const [slippagePctInput, setSlippagePctInput] = useState<string>("0.0001") // 默认0.01%

  const [backtestApiResponse, setBacktestApiResponse] = useState<BacktestResponse | null>(null)
  const [backtestApiError, setBacktestApiError] = useState<string | null>(null)

  const handleStrategyChange = useCallback((strategy: Strategy | null) => {
    setSelectedStrategy(strategy)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
    if (strategy && strategy.default_params) {
      setStrategyParameters(strategy.default_params)
    } else {
      setStrategyParameters({})
    }
    console.log("Selected strategy in App:", strategy)
  }, [])

  const handleParametersChange = useCallback((updatedParams: Record<string, any>) => {
    setStrategyParameters(updatedParams)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
    console.log("Parameters updated in App:", updatedParams)
  }, [])

  const handleStockSymbolsChange = useCallback((symbols: string) => {
    setStockSymbolsInput(symbols)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
    console.log("Stock symbols in App:", symbols)
  }, [])

  const handleStartDateChange = useCallback((date: string) => {
    setStartDate(date)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
    setEndDate(prevEndDate => {
      if (new Date(date) > new Date(prevEndDate)) {
        return date
      }
      return prevEndDate
    })
    console.log("Start date in App:", date)
  }, [])

  const handleEndDateChange = useCallback((date: string) => {
    setEndDate(date)
    setBacktestApiResponse(null)
    setBacktestApiError(null)
    console.log("End date in App:", date)
  }, [])

  const handleSlippagePctChange = useCallback((value: string) => {
    setSlippagePctInput(value)
    setBacktestApiResponse(null) // 清除旧结果
    setBacktestApiError(null)
    console.log("Slippage Pct in App:", value)
  }, [])

  const handleBacktestCompletion = useCallback((response: BacktestResponse | null, error?: string) => {
    if (error) {
      setBacktestApiError(error)
      setBacktestApiResponse(null)
      console.error("Backtest API Error in App:", error)
    } else if (response) {
      setBacktestApiResponse(response)
      setBacktestApiError(null)
      console.log("Backtest API Response in App:", response)
    }
  }, [])

  return (
    <Layout>
      {/* 主容器，采用 Flexbox 实现左右布局 */}
      <div className="flex flex-row flex-wrap md:flex-nowrap gap-6">
        {/* 左侧：回测配置区 */}
        <div className="w-full md:w-2/5 lg:w-1/3 flex flex-col gap-4 order-2 md:order-1 bg-white p-6 rounded-lg shadow-lg">
          
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
          
          {/* 新增：滑点输入 */}
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
          
          {/* 显示当前选中的日期和股票代码信息 - 保持简洁 */}
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
        </div>

        {/* 右侧：回测结果区 */}
        <div className="w-full md:w-3/5 lg:w-2/3 order-1 md:order-2 flex-grow">
          <ResultsDisplay response={backtestApiResponse} error={backtestApiError} />
        </div>
      </div>
    
    </Layout>
  )
}

export default App

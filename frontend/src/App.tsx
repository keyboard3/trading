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
      <div className="text-center">
        <div className="flex justify-center space-x-4 my-4">
          <a href="https://vitejs.dev" target="_blank" rel="noopener noreferrer">
            <img src={viteLogo} className="logo h-24" alt="Vite logo" />
          </a>
          <a href="https://react.dev" target="_blank" rel="noopener noreferrer">
            <img src={reactLogo} className="logo react h-24" alt="React logo" />
          </a>
        </div>
        <h1 className="text-blue-700 text-4xl font-bold my-4">回测配置区</h1>
        <div className="p-6 bg-white shadow-lg rounded-md max-w-lg mx-auto text-left">
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
          
          <div className="mb-4 p-2 bg-gray-50 rounded text-xs">
            <span className="font-semibold">日期范围:</span> {startDate} 至 {endDate}
          </div>
          
          {stockSymbolsInput && (
             <div className="mb-4 p-2 bg-gray-50 rounded text-xs">
               <span className="font-semibold">当前代码:</span> {stockSymbolsInput}
             </div>
          )}

          {selectedStrategy && (
            <div className="mt-4 p-3 bg-gray-50 rounded">
              <h3 className="text-md font-semibold text-gray-800">当前选中策略:</h3>
              <p className="text-sm text-gray-600">ID: {selectedStrategy.id}</p>
              <p className="text-sm text-gray-600">名称: {selectedStrategy.name}</p>
            </div>
          )}

          <ParametersForm 
            strategy={selectedStrategy} 
            onParametersChange={handleParametersChange} 
          />
          
          {selectedStrategy && Object.keys(strategyParameters).length > 0 && (
            <div className="mt-4 p-3 bg-gray-100 rounded">
              <h3 className="text-md font-semibold text-gray-800">当前参数值:</h3>
              <pre className="mt-2 text-xs bg-gray-200 p-2 rounded overflow-x-auto">
                {JSON.stringify(strategyParameters, null, 2)}
              </pre>
            </div>
          )}

          <RunBacktestButton
            strategyId={selectedStrategy?.id || null}
            stockSymbols={stockSymbolsInput}
            startDate={startDate}
            endDate={endDate}
            parameters={strategyParameters}
            onBacktestComplete={handleBacktestCompletion}
          />

          {/* <div className="mt-6">
            <button 
              onClick={() => setCount((count) => count + 1)}
              className="bg-indigo-500 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded transition duration-150 ease-in-out w-full"
            >
              示例计数器: {count}
            </button>
          </div> */}
        </div>

        <ResultsDisplay response={backtestApiResponse} error={backtestApiError} />
        
        <p className="mt-8 text-gray-500">
          Click on the Vite and React logos to learn more.
        </p>
      </div>
    </Layout>
  )
}

export default App

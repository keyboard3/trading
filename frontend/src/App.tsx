import { useState, useEffect, useCallback } from 'react'
import './App.css'
import Layout from './components/Layout'
// Backtest specific imports
import StrategySelector from './components/StrategySelector'
import type { Strategy } from './components/StrategySelector'
import ParametersForm from './components/ParametersForm'
// import StockInput from './components/StockInput' // Replaced with dropdown
import DateRangePicker from './components/DateRangePicker'
import RunBacktestButton from './components/RunBacktestButton'
import type { BacktestResponse } from './components/RunBacktestButton'
import ResultsDisplay from './components/ResultsDisplay'

// Simulation specific imports
import SimulationDisplay from './components/SimulationDisplay'
import StrategyControlPanel from './components/StrategyControlPanel' // Import StrategyControlPanel
import type { SimulationStatusResponse } from './types' // Assuming SimulationStatusResponse is in types.ts
import { fetchSimulationStatus, resumeSimulation } from './api' // Import fetchSimulationStatus AND resumeSimulation
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"; // Import Card components
import { Button } from "@/components/ui/button"; // Import Button
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"; // Import Alert components
import { Terminal } from "lucide-react"; // Import Terminal icon

// Define stock options
const STOCK_OPTIONS = [
  { label: "比亚迪-A股", value: "002594.SZ" },
  { label: "微软-美股", value: "MSFT" },
  { label: "苹果-美股", value: "AAPL" },
  // Add more stocks here as needed
  // { label: "腾讯控股-港股", value: "0700.HK" },
  // { label: "贵州茅台-A股", value: "600519.SS" },
];

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
  // Initialize with the value of the first stock option
  const [stockSymbolsInput, setStockSymbolsInput] = useState<string>(STOCK_OPTIONS[0].value) 
  const today = new Date()
  const oneYearAgo = new Date(new Date().setFullYear(today.getFullYear() - 1))
  const [startDate, setStartDate] = useState<string>(formatDate(oneYearAgo))
  const [endDate, setEndDate] = useState<string>(formatDate(today))
  const [slippagePctInput, setSlippagePctInput] = useState<string>("0.0001")
  const [backtestApiResponse, setBacktestApiResponse] = useState<BacktestResponse | null>(null)
  const [backtestApiError, setBacktestApiError] = useState<string | null>(null)

  // --- Tab and Simulation Shared States ---
  const [activeTab, setActiveTab] = useState<'backtest' | 'simulation'>('backtest');
  const [isSimulationRunningForControlPanel, setIsSimulationRunningForControlPanel] = useState<boolean>(false);
  const [currentStrategyNameForControlPanel, setCurrentStrategyNameForControlPanel] = useState<string | null>(null);
  const [refreshSimDisplayKey, setRefreshSimDisplayKey] = useState<number>(0);
  const [simulationStatus, setSimulationStatus] = useState<SimulationStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState<boolean>(true);
  const [isResuming, setIsResuming] = useState<boolean>(false); // State for resume action in App
  const [resumeError, setResumeError] = useState<string | null>(null); // State for resume error in App

  useEffect(() => {
    console.log("[App.tsx] refreshSimDisplayKey changed to:", refreshSimDisplayKey);
  }, [refreshSimDisplayKey]);

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

  // This callback now handles the value from the select dropdown
  const handleStockSymbolsChange = useCallback((selectedValue: string) => {
    setStockSymbolsInput(selectedValue);
    setBacktestApiResponse(null);
    setBacktestApiError(null);
  }, []);

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

  // --- Fetch simulation status periodically --- 
  useEffect(() => {
    let isMounted = true;
    const fetchStatus = async () => {
      try {
        const data = await fetchSimulationStatus();
        console.log("[App.tsx fetchStatus] Received data:", JSON.stringify(data)); // Log the received data
        if (isMounted) {
          setSimulationStatus(data);
          setStatusError(null);
        }
      } catch (err: any) {
        if (isMounted) {
          setStatusError(err.message || '获取模拟状态失败');
          setSimulationStatus(null);
        }
      } finally {
        if (isMounted) {
          setIsLoadingStatus(false); 
        }
      }
    };

    fetchStatus(); // Initial fetch
    const intervalId = setInterval(fetchStatus, 5000); // Poll every 5 seconds

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    }; // Cleanup on unmount
  }, []); // Empty dependency array means run once on mount and cleanup on unmount
  
  // --- Handler to manually refresh status after action --- 
  const refreshSimulationStatus = async () => {
      console.log("[App.tsx] refreshSimulationStatus called."); // Log when called
      setIsLoadingStatus(true); // Show loading indicator during refresh
      try {
        const data = await fetchSimulationStatus();
        setSimulationStatus(data);
        setStatusError(null);
      } catch (err: any) {
         setStatusError(err.message || '刷新模拟状态失败');
         setSimulationStatus(null);
      } finally {
         setIsLoadingStatus(false);
      }
  };

  // --- Handler for the resume action --- 
  const handleResumeSimulation = async () => {
      setIsResuming(true);
      setResumeError(null);
      try {
        const result = await resumeSimulation(); // Call API
        console.log(result.message);
        // Refresh status immediately after successful resume
        await refreshSimulationStatus(); 
      } catch (err: any) {
        const errorMessage = err.message || '恢复模拟失败';
        setResumeError(errorMessage);
        console.error(err);
      } finally {
        setIsResuming(false);
      }
  };

  // Helper to get current stock label
  const getCurrentStockLabel = () => {
    const selectedOption = STOCK_OPTIONS.find(option => option.value === stockSymbolsInput);
    return selectedOption ? selectedOption.label : stockSymbolsInput;
  };

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
              {/* Replace StockInput with a Select dropdown */}
              <div className="mt-0"> {/* Adjusted margin top */}
                <label htmlFor="stock-select" className="block text-sm font-medium text-gray-700 mb-1">
                  选择股票:
                </label>
                <select
                  id="stock-select"
                  value={stockSymbolsInput}
                  onChange={(e) => handleStockSymbolsChange(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                >
                  {STOCK_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label} ({option.value})
                    </option>
                  ))}
                </select>
              </div>
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
                {stockSymbolsInput && <div><span className="font-semibold">当前选股:</span> {getCurrentStockLabel()} ({stockSymbolsInput})</div>}
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
                stockSymbols={stockSymbolsInput} // This remains as a string
                startDate={startDate}
                endDate={endDate}
                parameters={strategyParameters}
                slippagePct={parseFloat(slippagePctInput) || 0}
                onBacktestComplete={handleBacktestCompletion}
              />
            </>
          )}

          {activeTab === 'simulation' && (
            <div className="space-y-4"> {/* Add spacing */} 
              {/* Conditional Rendering for Resume */} 
              {simulationStatus?.run_id && !simulationStatus?.is_simulation_running && (
                <Card>
                  <CardHeader>
                    <CardTitle>恢复模拟</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {resumeError && ( // Display resume error here
                       <Alert variant="destructive" className="mb-4">
                        <Terminal className="h-4 w-4" />
                        <AlertTitle>恢复失败</AlertTitle>
                        <AlertDescription>{resumeError}</AlertDescription>
                        <Button onClick={() => setResumeError(null)} variant="outline" size="sm" className="mt-2">
                          清除错误
                        </Button>
                      </Alert>
                    )} 
                    <p className="text-sm text-muted-foreground">
                        检测到先前停止的模拟 (Run ID: {simulationStatus.run_id}).
                    </p>
                    <Button 
                        onClick={handleResumeSimulation} 
                        disabled={isResuming}
                        className="w-full" // Make button full width
                    >
                        {isResuming ? '恢复中...' : '恢复模拟'}
                    </Button>
                     <p className="text-xs text-muted-foreground pt-1">
                        恢复将使用上次状态继续。要开始全新模拟，请使用下方控制面板。
                    </p>
                  </CardContent>
                </Card>
              )}

              {/* Strategy Control Panel */} 
              {/* Render always, but disable parts based on isResumable or isRunning */} 
              <StrategyControlPanel 
                onSimulationAction={refreshSimulationStatus} // Pass the refresh handler
                isRunning={simulationStatus?.is_simulation_running ?? false} // Use status from state
                isResumable={!!simulationStatus?.run_id && !simulationStatus?.is_simulation_running}
                currentStrategyName={simulationStatus?.active_strategy?.name}
              />
            </div>
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
            <div className="mt-4">
              {(isLoadingStatus && !simulationStatus) ? (
                  <p>加载模拟状态...</p>
              ) : statusError ? (
                  <p className="text-red-500">错误: {statusError}</p>
              ) : simulationStatus ? (
                  <SimulationDisplay 
                    // key={refreshSimDisplayKey} // Still commented out
                    initialStatus={simulationStatus}
                    // isLoading={isLoadingStatus} // Optional: pass to show internal spinner
                  />
              ) : (
                   <p className="text-muted-foreground">无模拟数据。请使用上方控制面板启动。</p>
              )}
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}

export default App;

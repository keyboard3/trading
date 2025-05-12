import React, { useState, useEffect, useCallback, useRef } from 'react';
import { fetchSimulationStatus } from '../api';
import type { SimulationStatusResponse, ApiRiskAlert } from '../types'; // Added ApiRiskAlert
import PortfolioSummary from './PortfolioSummary';
import HoldingsTable from './HoldingsTable';
import TradesList from './TradesList';
import StrategyInfoDisplay from './StrategyInfoDisplay';
import RiskAlertsDisplay from './RiskAlertsDisplay'; // Import the new component

const POLLING_INTERVAL_MS = 3000; // Poll every 3 seconds, was 5

interface SimulationDisplayProps {
  onDataRefreshed: (data: SimulationStatusResponse | null) => void; // Callback to App.tsx
  // refreshTriggerKey: number; // Key to trigger re-fetch, managed by App.tsx <SimulationDisplay key={...} />
}

const SimulationDisplay: React.FC<SimulationDisplayProps> = ({ onDataRefreshed }) => {
  const [simulationData, setSimulationData] = useState<SimulationStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true); // Start true for initial mount
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(false); // To track if component is still mounted for async operations

  // Stable data fetching function with no dependencies
  const fetchDataInternal = useCallback(async () => {
    try {
      const data = await fetchSimulationStatus();
      if (isMountedRef.current) {
        setSimulationData(data);
        setError(null); // Clear error on successful fetch
        onDataRefreshed(data); // Pass data up
      }
    } catch (err) {
      if (isMountedRef.current) {
        const errorMessage = err instanceof Error ? err.message : '获取模拟状态时发生未知错误。';
        setError(errorMessage);
        onDataRefreshed(null); // Pass null or error state up
        // On polling error, DO NOT set simulationData to null if stale data exists.
        console.error("Error fetching simulation status:", errorMessage);
      }
    }
  }, [onDataRefreshed]); // Added onDataRefreshed to dependencies

  // Effect for initial data load and setting up polling
  useEffect(() => {
    isMountedRef.current = true;
    setIsLoading(true); // Set loading for the very first fetch

    fetchDataInternal().finally(() => {
      if (isMountedRef.current) {
        setIsLoading(false); // Clear loading after the initial fetch completes
      }
    });

    const intervalId = setInterval(fetchDataInternal, POLLING_INTERVAL_MS);

    return () => {
      isMountedRef.current = false; // Cleanup on unmount
      clearInterval(intervalId);
    };
  }, [fetchDataInternal]); // Depends only on the stable fetchDataInternal

  // 1. Global Loading: Only for the very initial load or when a user action explicitly triggers it.
  if (isLoading && !simulationData && !error) { // Covers initial load before any data/error
    return <div className="p-6 text-center">模拟数据加载中...</div>;
  }

  // 2. Initial Error State: If initial load fails and no data was ever fetched.
  //    isLoading would be false here due to the .finally() in the initial load effect.
  if (error && !simulationData && !isLoading) {
    return (
      <div className="p-6 text-red-500 text-center">
        <p className="font-semibold">加载模拟数据显示失败:</p>
        <p>{error}</p>
        <p className="mt-2 text-sm text-gray-400">请检查后端服务或网络连接，或尝试通过左侧控制面板重新启动模拟。</p>
      </div>
    );
  }
  
  // 3. We have data (possibly stale) or are past initial load/error phase
  //    or isLoading is true due to a user action (handleSimulationActionRefresh) but we have prior data.
  return (
    <div className="space-y-6 p-1">
      {/* StrategyControlPanel is now rendered in App.tsx's left panel */}

      {/* Display a global loading overlay if isLoading is true due to a user action, even if stale data is present */} 
      {isLoading && (
        <div className="p-3 text-center text-gray-400 text-sm">正在更新状态...</div>
      )}

      {/* Display polling error message if any, while still showing stale data if available */}      
      {!isLoading && error && simulationData && ( // Show polling error only if not globally loading
        <div className="p-2 my-2 border border-red-500/50 rounded-md text-red-400 text-xs">
          <p><span className="font-medium">状态更新遇到问题:</span> {error}</p>
          <p className="mt-1">当前显示的数据可能已过时。系统将继续尝试自动刷新。</p>
        </div>
      )}

      {/* Render RiskAlertsDisplay if there are alerts, regardless of loading state for stale data */} 
      {simulationData && simulationData.risk_alerts && simulationData.risk_alerts.length > 0 && (
        <div className="my-4">
          <RiskAlertsDisplay alerts={simulationData.risk_alerts} />
        </div>
      )}

      {/* Display content based on simulationData - only if simulationData is not null and not globally loading for the initial time */} 
      {!isLoading && simulationData ? (
        // Display simulation details if portfolio_status exists, regardless of is_simulation_running
        // This allows showing the last state even if the simulation has been stopped.
        simulationData.portfolio_status ? (
          <div className="flex flex-row gap-4"> {/* Flex container for two columns */}
            <div className="flex-grow space-y-4" style={{ flexBasis: '65%' }}> {/* Main content area */}
              <div className="bg-gray-800 p-4 rounded-lg shadow-md">
                {/* Pass the actual running state to PortfolioSummary */}
                <PortfolioSummary 
                  portfolioStatus={simulationData.portfolio_status} 
                  isActuallyRunning={simulationData.is_simulation_running}
                  isLoading={false} 
                  error={null} />
              </div>
              <div className="bg-gray-800 p-4 rounded-lg shadow-md">
                <HoldingsTable holdings={simulationData.portfolio_status?.holdings || []} isLoading={false} error={null}/>
              </div>
              <div className="bg-gray-800 p-4 rounded-lg shadow-md">
                <TradesList trades={simulationData.recent_trades || []} isLoading={false} error={null}/>
              </div>
            </div>
            <div className="space-y-4" style={{ flexBasis: '35%' }}> {/* Sidebar for strategy info */}
              <div className="bg-gray-800 p-4 rounded-lg shadow-md">
                {/* StrategyInfoDisplay can still use active_strategy directly */}
                <StrategyInfoDisplay strategyInfo={simulationData.active_strategy || undefined} />
                {!simulationData.is_simulation_running && simulationData.active_strategy && (
                  <p className="text-xs text-yellow-400 italic mt-2 text-center">模拟已停止。显示的是最后状态。</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          // This case means simulationData exists but portfolio_status is null (e.g. after a full clear but before /status returns null portfolio)
          // OR it's the "no simulation running and no prior data" state from a fresh start.
          <div className="p-4 text-center text-gray-500 border-dashed border border-gray-600/70 rounded-md mt-4">
            <p className="text-sm">当前没有模拟在运行或无历史数据显示。请使用左侧的控制面板启动一个模拟。</p>
          </div>
        )
      ) : (
        // This state is when simulationData is null (initial load failed and no data, or never fetched)
        // and it's not initial loading (isLoading is false) and not an initial error (error is null).
        // This should ideally lead to the "no data" message above if fetchDataInternal sets simulationData to null on error.
        // However, the current fetchDataInternal does not set simulationData to null on polling error if stale data exists.
        // So this specific branch might be less frequently hit if an initial load succeeded once.
        !isLoading && !error && (
             <div className="p-4 text-center text-gray-500 border-dashed border border-gray-600/70 rounded-md mt-4">
                <p className="text-sm">无可用模拟数据。请尝试使用左侧的控制面板启动一个模拟。</p>
             </div>
        )
      )}
    </div>
  );
};

export default SimulationDisplay; 
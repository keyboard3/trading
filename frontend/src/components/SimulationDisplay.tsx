import React, { useState, useEffect, useCallback } from 'react';
import type { SimulationStatusResponse, ApiTradeRecord, TradeMarkerData } from '../types';
import PortfolioSummary from './PortfolioSummary';
import HoldingsTable from './HoldingsTable';
import TradesList from './TradesList';
import StrategyInfoDisplay from './StrategyInfoDisplay';
import RiskAlertsDisplay from './RiskAlertsDisplay';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import RealtimeChartDisplay from './charts/RealtimeChartDisplay';
import { fetchAllTradesForRun } from '../api';

const POLLING_INTERVAL_MS = 3000; // Poll every 3 seconds, was 5

interface SimulationDisplayProps {
  initialStatus: SimulationStatusResponse | null;
}

const SimulationDisplay: React.FC<SimulationDisplayProps> = ({ initialStatus }) => {
  const status = initialStatus;
  const [allTradesForChart, setAllTradesForChart] = useState<ApiTradeRecord[]>([]);
  const [isLoadingAllTrades, setIsLoadingAllTrades] = useState<boolean>(false);
  const [errorAllTrades, setErrorAllTrades] = useState<string | null>(null);

  useEffect(() => {
    console.log("[SimulationDisplay MOUNTED/UPDATED] Key: (from parent if passed), Props initialStatus changed or component mounted/updated. Current symbol:", status?.active_strategy?.parameters?.symbol);
    return () => {
      console.log("[SimulationDisplay UNMOUNTED] Current symbol before unmount:", status?.active_strategy?.parameters?.symbol);
    };
  }, [initialStatus]); // Assuming initialStatus is the main prop driving its content
  
  useEffect(() => {
    const currentRunId = status?.run_id;
    if (currentRunId) {
      console.log(`[SimulationDisplay] Detected runId: ${currentRunId}. Fetching all trades.`);
      setIsLoadingAllTrades(true);
      setErrorAllTrades(null);
      fetchAllTradesForRun(currentRunId)
        .then(fetchedTrades => {
          setAllTradesForChart(fetchedTrades);
          console.log(`[SimulationDisplay] Fetched ${fetchedTrades.length} historical trades for runId ${currentRunId}.`);
        })
        .catch(err => {
          console.error(`[SimulationDisplay] Error fetching all trades for runId ${currentRunId}:`, err);
          setErrorAllTrades(err.message || 'Failed to load all trades');
          setAllTradesForChart([]);
        })
        .finally(() => {
          setIsLoadingAllTrades(false);
        });
    } else {
      setAllTradesForChart([]);
      console.log("[SimulationDisplay] No runId, clearing allTradesForChart.");
    }
  }, [status?.run_id]);

  useEffect(() => {
    if (status && status.recent_trades) {
      if (!isLoadingAllTrades) {
        setAllTradesForChart(prevAllTrades => {
          const newTrades = status.recent_trades.filter(
            (recentTrade: ApiTradeRecord) => 
              !prevAllTrades.some(existingTrade => existingTrade.trade_id === recentTrade.trade_id)
          );
          if (newTrades.length > 0) {
            console.log(`[SimulationDisplay] Merging ${newTrades.length} new trades from recent_trades.`);
            return [...prevAllTrades, ...newTrades].sort((a, b) => a.timestamp - b.timestamp);
          }
          return prevAllTrades;
        });
      }
    }
  }, [status?.recent_trades, isLoadingAllTrades]);
  
  // --- Render Main Status Display --- 
  const renderStatusDetails = () => {
      if (!status || !status.portfolio_status) {
          if (status) {
             return (
                <Card>
                    <CardContent className="pt-6">
                        <p className="text-muted-foreground">
                           {status.is_simulation_running ? '模拟正在初始化或运行中，等待详细状态...' : '模拟未运行或无状态信息。请使用全局控制面板启动或恢复模拟。'}
                        </p>
                    </CardContent>
                </Card>
             );
          }
          return (
            <Card>
                <CardContent className="pt-6">
                    <p className="text-muted-foreground">无模拟状态信息。请使用全局控制面板启动或恢复模拟。</p>
                </CardContent>
            </Card>
          );
      }
      
      const chartSymbol = status.active_strategy?.parameters?.symbol || 
                        allTradesForChart?.[0]?.symbol ||
                        status.portfolio_status?.holdings?.[0]?.symbol;
      const chartInterval = "5m"; // Default interval

      // Prepare trades for RealtimeChartDisplay (map to TradeMarkerData)
      const tradesForChartDisplay: TradeMarkerData[] = allTradesForChart.map(trade => ({
        symbol: trade.symbol,
        timestamp: trade.timestamp,
        type: trade.type,
        price: trade.price,
        quantity: trade.quantity,
        // trade_id and total_value are not in TradeMarkerData, so they are omitted here
      }));

      return (
         <div className="space-y-4"> {/* Outer container for spacing between top and bottom */}
            {/* --- Realtime Chart --- */}
            {chartSymbol && (
                <Card>
                    <CardHeader>
                        <CardTitle>实时K线图: {chartSymbol} ({chartInterval})</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <RealtimeChartDisplay 
                            symbol={chartSymbol} 
                            interval={chartInterval} 
                            trades={tradesForChartDisplay}
                            runId={status.run_id}
                            latestTick={status.current_kline_for_chart || undefined}
                        />
                    </CardContent>
                </Card>
            )}

            {/* --- Top Row: Summary & Strategy/Risk --- */}
            {/* Change grid to 3 columns on medium screens, left takes 2, right takes 1 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4"> 
                {/* Left Cell: Portfolio Summary - Takes 2 columns */}
                <div className="md:col-span-2"> 
                    <PortfolioSummary 
                    portfolioStatus={status.portfolio_status}
                    isLoading={false}
                    error={null}
                    />
                </div>
                {/* Right Cell: Strategy Info & Risk Alerts - Takes 1 column */} 
                <div className="space-y-4">
                    {status.active_strategy && (
                    <StrategyInfoDisplay 
                        strategyInfo={status.active_strategy}
                    />
                    )}
                    <RiskAlertsDisplay alerts={status.risk_alerts || []} />
                </div>
            </div>

            {/* --- Bottom Row: Holdings & Trades --- */}
            {/* Change grid to simple div with spacing for vertical stacking */}
            <div className="space-y-4">
                 <HoldingsTable 
                   holdings={status.portfolio_status.holdings} 
                   isLoading={false}
                   error={null}
                 />
                <TradesList 
                  trades={allTradesForChart} 
                  isLoading={isLoadingAllTrades}
                  error={errorAllTrades}
                />
            </div>
         </div>
      );
  }

  // Main component return
  return (
    <div className="space-y-4">
      {renderStatusDetails()} {/* Always call renderStatusDetails */} 
    </div>
  );
};

export default SimulationDisplay; 
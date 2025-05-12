import React, { useState, useEffect, useCallback } from 'react';
import type { SimulationStatusResponse } from '../types';
import PortfolioSummary from './PortfolioSummary';
import HoldingsTable from './HoldingsTable';
import TradesList from './TradesList';
import StrategyInfoDisplay from './StrategyInfoDisplay';
import RiskAlertsDisplay from './RiskAlertsDisplay';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const POLLING_INTERVAL_MS = 3000; // Poll every 3 seconds, was 5

interface SimulationDisplayProps {
  initialStatus: SimulationStatusResponse | null; // Make required
}

const SimulationDisplay: React.FC<SimulationDisplayProps> = ({ initialStatus }) => {
  const status = initialStatus;
  
  // --- Render Main Status Display --- 
  const renderStatusDetails = () => {
      // Check if status or portfolio_status exists
      if (!status || !status.portfolio_status) {
          // If status exists but no portfolio, show simpler message
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
          // If status itself is null (and parent isn't showing loading/error), show generic message
          return (
            <Card>
                <CardContent className="pt-6">
                    <p className="text-muted-foreground">无模拟状态信息。请使用全局控制面板启动或恢复模拟。</p>
                </CardContent>
            </Card>
          );
      }
      
      // We have portfolio status, render the details
      return (
         <div className="space-y-4"> {/* Outer container for spacing between top and bottom */}
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
                 {/* <div> */} {/* No extra div needed for stacking */} 
                    <HoldingsTable 
                      holdings={status.portfolio_status.holdings} 
                      isLoading={false}
                      error={null}
                    />
                {/* </div> */}
                {/* <div> */} 
                    <TradesList 
                      trades={status.recent_trades} 
                      isLoading={false}
                      error={null}
                    />
                {/* </div> */}
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
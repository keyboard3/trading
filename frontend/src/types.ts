// frontend/src/types.ts

// Corresponds to backend Pydantic model: ApiTradeRecord
export interface ApiTradeRecord {
  trade_id: string;
  symbol: string;
  timestamp: number; // Assuming float timestamp from Python translates to number in JS/TS
  type: 'BUY' | 'SELL'; // Literal types for BUY or SELL
  quantity: number;
  price: number;
  total_value: number; // cost or proceeds
}

// Corresponds to backend Pydantic model: HoldingStatus
export interface HoldingStatus {
  symbol: string;
  quantity: number;
  average_cost_price: number;
  current_price?: number | null; // Allow null to align with backend Pydantic Optional[float]
  market_value?: number | null;
  unrealized_pnl?: number | null;
}

// Corresponds to backend Pydantic model: PortfolioStatusResponse
export interface PortfolioStatusResponse {
  cash: number;
  holdings_value: number;
  total_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  holdings: HoldingStatus[];
  asset_allocation: Record<string, number>; // e.g. {'MSFT': 40.0, 'AAPL': 60.0}
  is_running: boolean;
}

// Corresponds to backend Pydantic model: SignalEvent (simplified for frontend needs)
export interface SignalEvent {
    // Define based on what frontend needs if SignalEvents are displayed or used
    // For now, keeping it minimal or as defined by backend if directly used.
    type: string; // 'signal'
    symbol: string;
    timestamp: number;
    signal: 'BUY' | 'SELL' | 'HOLD';
    price: number;
}

// Corresponds to backend Pydantic model: ApiStrategyInfo
export interface ApiStrategyInfo {
  name: string;
  parameters: Record<string, any>;
}

// New interface for Risk Alerts
export interface ApiRiskAlert {
  alert_type: string;
  symbol?: string | null;
  message: string;
  timestamp: number; // Assuming Unix timestamp (float in Python -> number in TS)
}

// Corresponds to backend Pydantic model: SimulationStatusResponse
export interface SimulationStatusResponse {
  portfolio_status?: PortfolioStatusResponse | null;
  recent_trades: ApiTradeRecord[];
  active_strategy?: ApiStrategyInfo | null;
  is_simulation_running: boolean;
  risk_alerts?: ApiRiskAlert[] | null; // Add risk_alerts field
}

// For displaying available strategies from /api/simulation/available_strategies
export interface StrategyParameterSpec {
  name: string;
  type: string; // e.g., "int", "float", "str"
  required: boolean;
  default?: any;
  description?: string;
}

export interface AvailableStrategy {
  id: string;
  name: string;
  description: string;
  parameters: StrategyParameterSpec[];
}

// New interface for Start Simulation Request (corresponds to backend StartSimulationRequest Pydantic model)
export interface StartSimulationRequest {
  strategy_id: string;
  parameters: Record<string, any>;
  initial_capital?: number | null;
  risk_parameters?: Record<string, number> | null; // Add risk_parameters for the request
} 
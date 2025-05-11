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
  current_price?: number | null; // Optional, as backend might send null
  market_value?: number | null;
  unrealized_pnl?: number | null;
}

// Corresponds to backend Pydantic model: PortfolioStatusResponse
export interface PortfolioStatus {
  cash: number;
  holdings_value: number;
  total_value: number;
  holdings: HoldingStatus[];
  is_running: boolean;
}

// Corresponds to backend Pydantic model: ApiStrategyInfo
export interface ApiStrategyInfo {
  name: string;
  parameters: Record<string, any>; // Using Record<string, any> for a generic dictionary
}

// Corresponds to backend Pydantic model: SimulationStatusResponse
export interface SimulationStatusResponse {
  portfolio_status: PortfolioStatus | null; // Can be null if no simulation is running
  recent_trades: ApiTradeRecord[];
  active_strategy?: ApiStrategyInfo | null; 
  is_simulation_running: boolean; // Added to match backend
}

// --- New Types for Strategy Switching ---

// Corresponds to backend Pydantic model: StrategyParameterSpec
export interface StrategyParameterSpec {
  name: string;
  type: 'int' | 'float' | 'str'; // Assuming these are the common types for now
  required: boolean;
  default?: any;
  description?: string | null;
}

// Corresponds to backend Pydantic model: AvailableStrategy
export interface AvailableStrategy {
  id: string;
  name: string;
  description: string;
  parameters: StrategyParameterSpec[];
}

// Payload for starting a simulation
export interface StartSimulationPayload {
  strategy_id: string;
  parameters: Record<string, any>;
  initial_capital?: number; // Optional initial capital
}

// Generic message response from backend (e.g., for start/stop simulation)
export interface BackendResponseMessage {
  message: string;
  // Optionally, include other fields if the backend sends more details
  // error?: string;
} 
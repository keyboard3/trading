from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field # Field for default values etc.
from typing import List, Dict, Any, Optional
import os
import shutil
import datetime
import uuid
import time # Added for simulation
import asyncio # Added for periodic saving task
import json # Added for saving state
# import threading # Not directly needed for now as provider manages its own thread

# --- Import LogColors ---
# Moved this block higher to ensure LogColors is defined regardless of other import issues
import sys
# Assuming logger_utils is in the same backend directory
try:
    from .logger_utils import LogColors # Use relative import if in the same package
except ImportError:
    # Fallback if relative import fails (e.g., running script directly)
    try:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from backend.logger_utils import LogColors
    except ImportError:
        print("CRITICAL: Could not import LogColors from backend.logger_utils. Colored logs will be disabled in main_api.")
        # Define fallback class if import fails completely
        class LogColors:
            HEADER = ''
            OKBLUE = ''
            OKCYAN = ''
            OKGREEN = ''
            WARNING = ''
            FAIL = ''
            ENDC = ''
            BOLD = ''
            UNDERLINE = ''

# --- Import from main.py & core_engine ---
# Ensure main.py is in PYTHONPATH or adjust path accordingly if needed.
# Assuming main.py is in the parent directory for now, adjust if structure is different
# --- This sys.path modification might be redundant if LogColors import worked, but keep for core imports ---
project_root_for_core = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root_for_core not in sys.path:
     sys.path.append(project_root_for_core) # Add parent dir to sys.path

try:
    from main import (
        execute_single_backtest_run, 
        STRATEGY_CONFIG as MAIN_STRATEGY_CONFIG, # Use imported one
        RESULTS_DIR as MAIN_RESULTS_DIR,         # Use imported one
        init_db as main_init_db,                 # Use imported one
        COMMISSION_RATE_PCT as DEFAULT_COMMISSION_RATE,
        MIN_COMMISSION_PER_TRADE as DEFAULT_MIN_COMMISSION,
        INITIAL_CAPITAL as DEFAULT_INITIAL_CAPITAL,
        DEFAULT_SLIPPAGE_PCT
    )
    # Attempt to import core engine components for simulation
    from core_engine.portfolio import MockPortfolio
    from core_engine.trading_engine import MockTradingEngine, SignalEvent, TradeRecord # SignalEvent/TradeRecord for Pydantic models
    from core_engine.realtime_feed import MockRealtimeDataProvider
    from core_engine.realtime_data_providers import YahooFinanceDataProvider
    from strategies.simple_ma_strategy import RealtimeSimpleMAStrategy
    from strategies.realtime_rsi_strategy import RealtimeRSIStrategy # Add import for RSI strategy
    from core_engine.risk_manager import RiskAlert # Import RiskAlert
    from core_engine.historical_data_provider import fetch_historical_klines_core # <--- ADD THIS IMPORT
    from core_engine.realtime_klines_aggregator import RealtimeKlinesAggregator, KLineData as AggregatorKLineData 
except ImportError as e:
    print(f"Error importing from main.py or core_engine: {e}")
    # Fallbacks (existing + new for simulation components)
    MAIN_STRATEGY_CONFIG = {"ERROR": {"description": "Failed to load STRATEGY_CONFIG from main.py"}}
    MAIN_RESULTS_DIR = "results_fallback" 
    def main_init_db(): print("Warning: main_init_db not loaded.")
    DEFAULT_COMMISSION_RATE = 0.0005
    DEFAULT_MIN_COMMISSION = 5.0
    DEFAULT_INITIAL_CAPITAL = 100000.0
    DEFAULT_SLIPPAGE_PCT = 0.001
    def execute_single_backtest_run(*args, **kwargs): 
        return {"error": "execute_single_backtest_run not loaded"}
    # Fallbacks for simulation components if imports fail
    MockPortfolio = None
    MockTradingEngine = None
    MockRealtimeDataProvider = None
    RealtimeSimpleMAStrategy = None
    RealtimeRSIStrategy = None # Add fallback for RSI strategy
    SignalEvent = Dict # Fallback type
    TradeRecord = Dict # Fallback type
    RiskAlert = Any # Fallback type for RiskAlert
    RealtimeKlinesAggregator = None 
    AggregatorKLineData = Dict 


# Remove the local, simplified STRATEGY_CONFIG
# STRATEGY_CONFIG = { ... } 

app = FastAPI()

# --- CORS Middleware ---
# This must be added before any routes are defined.
# It allows requests from your frontend development server (e.g., http://localhost:5173)
origins = [
    "*", # Your frontend's origin
    # You can add other origins here if needed, e.g., your production frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Allows cookies to be included in requests
    allow_methods=["*"],    # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],    # Allows all headers
)
# --- Constants for API ---
API_RUNS_SUBDIR_NAME = "api_runs" # Subdirectory within MAIN_RESULTS_DIR for API specific runs
API_RESULTS_MOUNT_PATH = f"/{API_RUNS_SUBDIR_NAME}" # Web path to access these results

# --- Constants for Persistence ---
SIMULATION_RUNS_BASE_DIR = "results/simulation_runs" # Base directory for all simulation runs
SIMULATION_STATE_FILENAME = "simulation_state.json"
SAVE_INTERVAL_SECONDS = 60 # Save state every 60 seconds

# --- Global Simulation State Variables ---
# Refactored Global Simulation State
simulation_components: Dict[str, Any] = {
    "portfolio": None,
    "engine": None,
    "data_provider": None,
    "strategy": None,
    "strategy_info": None, # Will store an ApiStrategyInfo instance
    "running": False,
    "run_id": None, # Added to store the unique ID for the current run
    "save_task": None, # Added to store the background save task
    "klines_aggregator": None, # NEW: Instance of RealtimeKlinesAggregator
    "current_chart_interval_for_aggregator": "5m", # NEW: Store the chart interval, default to 5m
}
# Lock for thread-safe access to simulation state if needed later
# simulation_lock = threading.Lock()

# --- Risk Management Parameters (Global Constants for now) ---
RISK_MAX_UNREALIZED_LOSS_PER_POSITION_PERCENTAGE: float = 0.10 # 10% loss tolerance per position
RISK_MAX_POSITION_SIZE_PERCENTAGE_OF_PORTFOLIO: float = 0.25  # Max 25% of portfolio value in a single asset
RISK_MAX_ACCOUNT_DRAWDOWN_PERCENTAGE: float = 0.15             # Max 15% drawdown from peak portfolio value

# --- Pydantic Models for Simulation API --- 
class HoldingStatus(BaseModel):
    symbol: str
    quantity: int
    average_cost_price: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None

class PortfolioStatusResponse(BaseModel):
    cash: float
    holdings_value: float # Market value of all holdings
    total_value: float    # cash + holdings_value
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    holdings: List[HoldingStatus] # This will now use the enhanced HoldingStatus
    asset_allocation: Dict[str, float] = {} # e.g. {'MSFT': 40.0, 'AAPL': 60.0}
    is_running: bool # Kept from previous version, indicates if data provider/strategy is active

# Re-using TradeRecord structure from trading_engine, but defining a Pydantic model for API clarity
class ApiTradeRecord(BaseModel):
    trade_id: str
    symbol: str
    timestamp: float
    type: str # BUY or SELL
    quantity: int
    price: float
    total_value: float # cost or proceeds

class ApiStrategyInfo(BaseModel): # New model for strategy info
    name: str
    parameters: Dict[str, Any]

# Pydantic model for RiskAlert to be used in API responses
class ApiRiskAlert(BaseModel):
    alert_type: str
    symbol: Optional[str] = None
    message: str
    timestamp: float

# --- Pydantic Model for K-Line Data ---
class KLineData(BaseModel):
    time: int  # UNIX timestamp (seconds, UTC)
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0 # Changed to Optional[float] with default

class SimulationStatusResponse(BaseModel):
    portfolio_status: Optional[PortfolioStatusResponse] = None # Made optional
    recent_trades: List[ApiTradeRecord] = [] # Default to empty list
    active_strategy: Optional[ApiStrategyInfo] = None 
    is_simulation_running: bool # New field to clearly indicate if any simulation is running
    risk_alerts: Optional[List[ApiRiskAlert]] = None # New field for risk alerts
    run_id: Optional[str] = None # Added field to indicate if a resumable run exists
    current_kline_for_chart: Optional[KLineData] = None # NEW FIELD

# --- New Pydantic Models for Strategy Switching ---
class StrategyParameterSpec(BaseModel):
    name: str
    type: str # e.g., "int", "float", "str"
    required: bool
    default: Optional[Any] = None
    description: Optional[str] = None

class AvailableStrategy(BaseModel):
    id: str # Unique identifier for the strategy
    name: str # User-friendly name
    description: str
    parameters: List[StrategyParameterSpec]

class StartSimulationRequest(BaseModel):
    strategy_id: str
    parameters: Dict[str, Any]
    initial_capital: Optional[float] = Field(None, gt=0, description="Optional initial capital for the simulation (must be > 0 if provided)")
    risk_parameters: Optional[Dict[str, float]] = Field(None, description="Optional risk parameters for the simulation. Keys: 'stop_loss_pct', 'max_pos_pct', 'max_dd_pct'")
    data_provider_type: Optional[str] = Field("mock", description="Type of data provider: 'mock' or 'yahoo'. Default is 'mock'.")
    yahoo_polling_interval: Optional[int] = Field(60, gt=0, description="Polling interval in seconds for Yahoo Finance provider (must be > 0).")


# --- Strategy Registry ---
# This will hold metadata about discoverable strategies
# For now, we manually register RealtimeSimpleMAStrategy
# In the future, this could be populated by scanning a directory or a config file

# Ensure RealtimeSimpleMAStrategy is imported
if RealtimeSimpleMAStrategy is None:
    print("CRITICAL: RealtimeSimpleMAStrategy not imported. Strategy switching will not work for MA.")
if RealtimeRSIStrategy is None: # Check for RSI strategy import
    print("CRITICAL: RealtimeRSIStrategy not imported. Strategy switching will not work for RSI.")

STRATEGY_REGISTRY: Dict[str, AvailableStrategy] = {}

if RealtimeSimpleMAStrategy is not None:
    STRATEGY_REGISTRY["realtime_simple_ma"] = AvailableStrategy(
        id="realtime_simple_ma",
        name="实时简单移动平均线策略",
        description="一个简单的实时交易策略，使用两条移动平均线的交叉来产生买入/卖出信号。",
        parameters=[
            StrategyParameterSpec(name="symbol", type="str", required=True, default="MSFT", description="要交易的股票代码 (例如: \'SIM_STOCK_A\')"),
            StrategyParameterSpec(name="short_window", type="int", required=True, default=5, description="短期移动平均线的窗口大小"),
            StrategyParameterSpec(name="long_window", type="int", required=True, default=10, description="长期移动平均线的窗口大小"),
        ]
    )

if RealtimeRSIStrategy is not None: # Add RSI strategy to registry
    STRATEGY_REGISTRY["realtime_rsi"] = AvailableStrategy(
        id="realtime_rsi",
        name="实时RSI震荡策略",
        description="根据相对强弱指数 (RSI) 在超买超卖区域的交叉产生交易信号。",
        parameters=[
            StrategyParameterSpec(name="symbol", type="str", required=True, default="MSFT", description="要交易的股票代码 (例如: \'SIM_STOCK_B\')"),
            StrategyParameterSpec(name="period", type="int", required=True, default=14, description="RSI 计算周期长度"),
            StrategyParameterSpec(name="oversold_threshold", type="float", required=True, default=30.0, description="RSI 超卖阈值"),
            StrategyParameterSpec(name="overbought_threshold", type="float", required=True, default=70.0, description="RSI 超买阈值"),
        ]
    )

# Add more strategies here as they are developed

# --- Helper function to save simulation state --- 
async def save_simulation_state(run_id: Optional[str]):
    if not run_id:
        print(f"{LogColors.WARNING}BACKEND_API: save_simulation_state called without run_id. Skipping.{LogColors.ENDC}")
        return

    global simulation_components
    portfolio = simulation_components.get("portfolio")
    engine = simulation_components.get("engine")

    if not portfolio or not engine:
        print(f"{LogColors.WARNING}BACKEND_API: Portfolio or Engine not available for saving state (Run ID: {run_id}). Skipping.{LogColors.ENDC}")
        return

    try:
        portfolio_state = portfolio.to_dict()
        engine_state = engine.to_dict()
        
        combined_state = {
            "run_id": run_id,
            "timestamp": time.time(),
            "portfolio_state": portfolio_state,
            "engine_state": engine_state,
            # Optionally add strategy info if needed for restore
            "strategy_info": simulation_components.get("strategy_info").dict() if simulation_components.get("strategy_info") else None
        }
        
        save_dir = os.path.join(SIMULATION_RUNS_BASE_DIR, run_id)
        os.makedirs(save_dir, exist_ok=True) # Ensure directory exists
        save_path = os.path.join(save_dir, SIMULATION_STATE_FILENAME)
        
        # Use async file writing if possible, or run sync write in thread executor
        # For simplicity here, using standard sync write (might block briefly)
        with open(save_path, 'w') as f:
            json.dump(combined_state, f, indent=4)
            
        if simulation_components.get("engine", {}).verbose: # Check if engine exists and is verbose
             print(f"{LogColors.OKGREEN}BACKEND_API: Simulation state saved successfully to {save_path}{LogColors.ENDC}")
            
    except Exception as e:
        print(f"{LogColors.FAIL}BACKEND_API: Error saving simulation state for run_id {run_id}: {e}{LogColors.ENDC}")

# --- Background Task for Periodic Saving --- 
async def _periodic_save_task(run_id: str):
    while True:
        try:
            # Check if simulation is still supposed to be running for this run_id
            if not simulation_components["running"] or simulation_components.get("run_id") != run_id:
                print(f"{LogColors.OKBLUE}BACKEND_API: Periodic save task for run_id {run_id} stopping as simulation is no longer active or run_id changed.{LogColors.ENDC}")
                break # Exit the loop
            
            await save_simulation_state(run_id)
            await asyncio.sleep(SAVE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            print(f"{LogColors.OKBLUE}BACKEND_API: Periodic save task for run_id {run_id} cancelled.{LogColors.ENDC}")
            break # Exit loop on cancellation
        except Exception as e:
            print(f"{LogColors.FAIL}BACKEND_API: Error in periodic save task for run_id {run_id}: {e}. Task will attempt to continue.{LogColors.ENDC}")
            # Decide whether to break or continue after error
            await asyncio.sleep(SAVE_INTERVAL_SECONDS) # Wait before retrying/continuing


# --- Helper function to stop current simulation ---
def stop_current_simulation(clear_all_components: bool = False):
    global simulation_components
    current_run_id = simulation_components.get("run_id")
    
    # --- Cancel existing save task --- 
    save_task = simulation_components.get("save_task")
    if save_task and not save_task.done():
        print(f"{LogColors.OKBLUE}BACKEND_API: Cancelling periodic save task for run_id {current_run_id}...{LogColors.ENDC}")
        save_task.cancel()
        # We might want to await briefly here, but cancellation should be enough
        # try:
        #     await asyncio.wait_for(save_task, timeout=1.0) 
        # except (asyncio.CancelledError, asyncio.TimeoutError):
        #     pass
        simulation_components["save_task"] = None # Clear the task reference
        
    if simulation_components["running"] or clear_all_components:
        print(f"BACKEND_API: stop_current_simulation called. clear_all_components={clear_all_components}, run_id={current_run_id}")
        
        active_strategy = simulation_components.get("strategy")
        if active_strategy:
            try:
                print("BACKEND_API: Stopping strategy...")
                active_strategy.stop()
            except Exception as e:
                print(f"BACKEND_API: Error stopping strategy: {e}")
            if clear_all_components: 
                simulation_components["strategy"] = None

        active_data_provider = simulation_components.get("data_provider")
        if active_data_provider:
            try:
                print("BACKEND_API: Stopping data provider...")
                active_data_provider.stop()
            except Exception as e:
                print(f"BACKEND_API: Error stopping data provider: {e}")
            if clear_all_components: 
                simulation_components["data_provider"] = None

        # --- Perform Final Save before clearing (if not clearing all) ---
        was_running = simulation_components["running"] # Check status before changing it
        simulation_components["running"] = False # Mark as not running *before* final save for consistency
        print("BACKEND_API: Simulation marked as not running.")

        if was_running and not clear_all_components and current_run_id: # Save only if it was running and we are not clearing everything
            print(f"{LogColors.OKBLUE}BACKEND_API: Performing final state save for run_id {current_run_id}...{LogColors.ENDC}")
            # Need to run async save in a way sync function can call
            # Simplest might be to run it in the event loop if available
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                     # Schedule it and let it run, don't wait necessarily
                     loop.create_task(save_simulation_state(current_run_id))
                else:
                     # Fallback for shutdown scenario maybe? Or just log.
                     print(f"{LogColors.WARNING}BACKEND_API: Event loop not running, cannot schedule final async save for {current_run_id}.{LogColors.ENDC}")
            except Exception as e_save:
                 print(f"{LogColors.FAIL}BACKEND_API: Error scheduling final save for {current_run_id}: {e_save}{LogColors.ENDC}")
        
        if clear_all_components:
            print("BACKEND_API: Clearing portfolio, engine, and strategy_info.")
            simulation_components["portfolio"] = None
            simulation_components["engine"] = None
            simulation_components["strategy_info"] = None
            simulation_components["run_id"] = None # Clear run_id when clearing all
            print("BACKEND_API: All simulation components cleared.")
            # If clearing all components, also reset or clear the klines aggregator state.
            klines_aggregator = simulation_components.get("klines_aggregator")
            if klines_aggregator and hasattr(klines_aggregator, 'reset_all'):
                klines_aggregator.reset_all()
                print(f"{LogColors.OKCYAN}[API stop_current_simulation] Klines aggregator reset due to clear_all_components=True.{LogColors.ENDC}")
            simulation_components["klines_aggregator"] = None # Optionally set to None if fully clearing
        else:
            print("BACKEND_API: Active components (strategy, data_provider) stopped. Portfolio/Engine/run_id state retained.")

        # We already marked running = False earlier
        # print("BACKEND_API: Simulation marked as not running.") # Redundant


# --- App Startup Event ---
@app.on_event("startup")
async def startup_event():
    print("FastAPI application startup...")
    print("Initializing database...")
    main_init_db() # Call init_db from main.py
    
    # Ensure the main results directory and the API specific subdirectory exist
    api_runs_full_path = os.path.join(MAIN_RESULTS_DIR, API_RUNS_SUBDIR_NAME)
    if not os.path.exists(api_runs_full_path):
        try:
            os.makedirs(api_runs_full_path)
            print(f"Created API results directory: {api_runs_full_path}")
        except OSError as e:
            print(f"Error creating API results directory {api_runs_full_path}: {e}")
    
    # Ensure the simulation runs base directory exists
    if not os.path.exists(SIMULATION_RUNS_BASE_DIR):
        try:
            os.makedirs(SIMULATION_RUNS_BASE_DIR)
            print(f"Created simulation runs base directory: {SIMULATION_RUNS_BASE_DIR}")
        except OSError as e:
            print(f"Error creating simulation runs base directory {SIMULATION_RUNS_BASE_DIR}: {e}")
    
    # --- Attempt to restore latest simulation state --- 
    print(f"{LogColors.OKBLUE}Attempting to restore latest simulation state...{LogColors.ENDC}")
    try:
        latest_state_file = find_latest_simulation_state_file(SIMULATION_RUNS_BASE_DIR)
        if latest_state_file:
            print(f"Found latest state file: {latest_state_file}")
            with open(latest_state_file, 'r') as f:
                state_data = json.load(f)
                
            portfolio_state = state_data.get("portfolio_state")
            engine_state = state_data.get("engine_state")
            run_id = state_data.get("run_id")
            strategy_info_dict = state_data.get("strategy_info")

            if portfolio_state and engine_state and run_id:
                if MockPortfolio is None or MockTradingEngine is None:
                     print(f"{LogColors.FAIL}Cannot restore state: MockPortfolio or MockTradingEngine not loaded.{LogColors.ENDC}")
                else:
                    restored_portfolio = MockPortfolio.from_dict(portfolio_state)
                    
                    # Define a safe price callback for the restored engine (no active data provider)
                    def get_price_callback_for_restored_engine(symbol: str) -> Optional[float]:
                        # Maybe try to find last known price from portfolio state if needed?
                        # For now, returning None as provider is inactive.
                        return None
                        
                    restored_engine = MockTradingEngine.from_dict(
                        engine_state,
                        restored_portfolio, # Pass the restored portfolio
                        get_price_callback_for_restored_engine # Pass safe callback
                    )
                    
                    # Restore components into global state
                    global simulation_components
                    simulation_components["portfolio"] = restored_portfolio
                    simulation_components["engine"] = restored_engine
                    simulation_components["run_id"] = run_id
                    simulation_components["running"] = False # Restored state is not running
                    simulation_components["data_provider"] = None # Ensure no stale provider reference
                    simulation_components["strategy"] = None # Ensure no stale strategy reference
                    simulation_components["save_task"] = None # Ensure no stale save task
                    
                    if strategy_info_dict:
                        try:
                            simulation_components["strategy_info"] = ApiStrategyInfo(**strategy_info_dict)
                        except Exception as e_strat_info:
                            print(f"{LogColors.WARNING}Could not restore ApiStrategyInfo from state: {e_strat_info}{LogColors.ENDC}")
                            simulation_components["strategy_info"] = None
                    else:
                         simulation_components["strategy_info"] = None
                         
                    print(f"{LogColors.OKGREEN}Successfully restored simulation state for run_id: {run_id}{LogColors.ENDC}")
            else:
                print(f"{LogColors.WARNING}State file {latest_state_file} is incomplete. Skipping restore.{LogColors.ENDC}")
        else:
            print("No previous simulation state file found to restore.")
            
    except Exception as e:
        print(f"{LogColors.FAIL}Error during simulation state restoration: {e}. Starting with fresh state.{LogColors.ENDC}")
        # Ensure components are cleared if restoration fails mid-way
        simulation_components = {
            "portfolio": None, "engine": None, "data_provider": None, 
            "strategy": None, "strategy_info": None, "running": False, 
            "run_id": None, "save_task": None
        }

    # Mount static files directory for API results (after potential state restoration)
    # This allows accessing files like http://localhost:8089/api_runs/<run_id>/report.txt
    app.mount(API_RESULTS_MOUNT_PATH, 
              StaticFiles(directory=api_runs_full_path), 
              name="api_results_static")
    print(f"Static files mounted from '{api_runs_full_path}' at '{API_RESULTS_MOUNT_PATH}'")

    print("Startup complete.")


@app.on_event("shutdown")
async def shutdown_event():
    # global simulation_running, simulation_strategy_A, simulation_data_provider # Old globals
    print("FastAPI application shutdown...")
    # --- Perform Final Save on Shutdown --- 
    current_run_id = simulation_components.get("run_id")
    was_running = simulation_components.get("running", False)
    if was_running and current_run_id:
        print(f"{LogColors.OKBLUE}BACKEND_API: Performing final state save during shutdown for run_id {current_run_id}...{LogColors.ENDC}")
        # Run save synchronously during shutdown if possible, or at least attempt
        try:
            await save_simulation_state(current_run_id) # Try awaiting directly
        except Exception as e_save:
            print(f"{LogColors.FAIL}BACKEND_API: Error during final save on shutdown for {current_run_id}: {e_save}{LogColors.ENDC}")
            
    stop_current_simulation(clear_all_components=True) # Clear everything on full shutdown
    # if simulation_running:
    #     print("Stopping global simulation components...")
    #     if simulation_strategy_A:
    #         simulation_strategy_A.stop()
    #     if simulation_data_provider:
    #         simulation_data_provider.stop()
    #     simulation_running = False
    #     print("Global simulation stopped.")

class BacktestRequest(BaseModel):
    strategy_id: str
    tickers: List[str]
    start_date: str  # Expected format: "YYYY-MM-DD"
    end_date: str    # Expected format: "YYYY-MM-DD"
    initial_capital: float = DEFAULT_INITIAL_CAPITAL # Use default from main
    parameters: Dict[str, Any]
    # Optional commission override, otherwise use defaults from main.py
    commission_rate_pct: float = DEFAULT_COMMISSION_RATE
    min_commission_per_trade: float = DEFAULT_MIN_COMMISSION
    slippage_pct: float = None # 新增：可选的滑点百分比


@app.get("/api/v1/strategies")
async def get_strategies():
    """获取所有可用策略及其配置信息"""
    if "ERROR" in MAIN_STRATEGY_CONFIG:
         raise HTTPException(status_code=500, detail="Strategy configuration could not be loaded.")
    # Return a "cleaned" version suitable for API (e.g., without function objects if any were there)
    # Our STRATEGY_CONFIG from main.py is already clean (uses module/function names)
    return MAIN_STRATEGY_CONFIG

@app.get("/")
async def read_root():
    return {"message": "量化交易平台后端API运行中"}

@app.post("/api/v1/backtest/run")
async def run_backtest_api(request: BacktestRequest):
    """
    接收回测请求，为每个股票代码触发核心回测引擎，并返回结果链接。
    """
    print(f"接收到API回测请求 for strategy {request.strategy_id} on symbols: {request.tickers}")

    if request.strategy_id not in MAIN_STRATEGY_CONFIG:
        raise HTTPException(status_code=404, detail=f"Strategy '{request.strategy_id}' not found.")
    
    selected_strategy_config_details = MAIN_STRATEGY_CONFIG[request.strategy_id]

    # Create a unique directory for this API run
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    # Sanitize strategy_id and first symbol for a more readable directory name
    safe_strategy_id = "".join(c if c.isalnum() else "_" for c in request.strategy_id)
    safe_first_symbol = "".join(c if c.isalnum() else "_" for c in request.tickers[0]) if request.tickers else "multi"
    
    run_tag = f"{safe_strategy_id}_{safe_first_symbol}_{timestamp}_{unique_id}"
    
    current_api_run_results_dir = os.path.join(MAIN_RESULTS_DIR, API_RUNS_SUBDIR_NAME, run_tag)
    
    try:
        os.makedirs(current_api_run_results_dir, exist_ok=True)
        print(f"Created results directory for API run: {current_api_run_results_dir}")
    except OSError as e:
        print(f"Error creating directory {current_api_run_results_dir}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not create results directory on server: {e}")

    all_symbol_results = []

    for symbol_to_run in request.tickers:
        print(f"  Processing symbol: {symbol_to_run} for strategy: {request.strategy_id}")
        
        # Call the core backtest execution function from main.py
        try:
            single_run_result = execute_single_backtest_run(
                symbol=symbol_to_run,
                strategy_id=request.strategy_id,
                strategy_specific_params=request.parameters,
                selected_strategy_config=selected_strategy_config_details,
                results_output_dir=current_api_run_results_dir, # Pass the unique dir for this API run
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.initial_capital,
                commission_rate_pct=request.commission_rate_pct,
                min_commission_per_trade=request.min_commission_per_trade,
                slippage_pct=request.slippage_pct if request.slippage_pct is not None else DEFAULT_SLIPPAGE_PCT
            )
        except Exception as e_exec:
            print(f"Exception during execute_single_backtest_run for {symbol_to_run}: {e_exec}")
            single_run_result = {"error": f"Execution failed for {symbol_to_run}: {str(e_exec)}", "metrics": None}


        # Construct web-accessible URLs for report and charts if paths are returned
        api_accessible_result = {
            "ticker": symbol_to_run,
            "metrics": single_run_result.get("metrics"),
            "error": single_run_result.get("error"),
            "report_url": None,
            "portfolio_value_chart_url": None,
            "strategy_chart_url": None,
        }

        if single_run_result.get("report_path"):
            api_accessible_result["report_url"] = f"{API_RESULTS_MOUNT_PATH}/{run_tag}/{single_run_result['report_path']}"
        if single_run_result.get("portfolio_value_chart_path"):
            api_accessible_result["portfolio_value_chart_url"] = f"{API_RESULTS_MOUNT_PATH}/{run_tag}/{single_run_result['portfolio_value_chart_path']}"
        if single_run_result.get("strategy_chart_path"):
            api_accessible_result["strategy_chart_url"] = f"{API_RESULTS_MOUNT_PATH}/{run_tag}/{single_run_result['strategy_chart_path']}"
        
        all_symbol_results.append(api_accessible_result)

    return {
        "message": f"Backtest processing completed for strategy '{request.strategy_id}'.",
        "run_id_tag": run_tag, # Useful for client to find results folder if needed
        "results_base_url": f"{API_RESULTS_MOUNT_PATH}/{run_tag}/", # Base URL for this run's artifacts
        "results_per_symbol": all_symbol_results
    }

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # 原来的可能只是: return JSONResponse(...)
    print(f"Request body: {await request.body()}") # 打印原始请求体
    print(f"Validation errors: {exc.errors()}")   # 打印详细的Pydantic验证错误
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}, # 也可以考虑将错误详情返回给前端
    )

# --- Simulation Status Endpoint --- 
@app.get("/api/simulation/status", response_model=SimulationStatusResponse)
async def get_simulation_status(chart_interval: str = Query("5m", description="Chart interval for K-line data e.g., 1m, 5m, 1h, 1d")):
    active_sim_components = simulation_components
    
    # Store the requested chart_interval for data providers to use
    active_sim_components["current_chart_interval_for_aggregator"] = chart_interval

    if not active_sim_components or not active_sim_components.get("portfolio"):
        return SimulationStatusResponse(
            is_simulation_running=bool(active_sim_components.get("running")),
            run_id=active_sim_components.get("run_id")
        )

    portfolio = active_sim_components["portfolio"]
    engine = active_sim_components.get("engine")
    strategy_info = active_sim_components.get("strategy_info")
    is_running_flag = bool(active_sim_components.get("running"))
    current_run_id = active_sim_components.get("run_id")
    klines_aggregator = active_sim_components.get("klines_aggregator") # Get the aggregator

    # --- Construct portfolio_status (This part is simplified for the edit, original logic should be preserved) ---
    portfolio_data_for_response: Optional[PortfolioStatusResponse] = None
    if portfolio:
        holdings_value = 0
        current_unrealized_pnl = 0
        holdings_data_list: List[HoldingStatus] = []
        data_provider_for_prices = active_sim_components.get("data_provider")

        for symbol_h, holding_info in portfolio.holdings.items():
            live_price = None
            if data_provider_for_prices and hasattr(data_provider_for_prices, "get_current_price") and is_running_flag:
                live_price = data_provider_for_prices.get_current_price(symbol_h)
            if live_price is None: # Fallback if provider can't give price or not running
                 live_price = portfolio.get_last_known_price(symbol_h)

            market_val = None
            unrealized_pnl_val = None
            if live_price is not None:
                market_val = holding_info.quantity * live_price
                unrealized_pnl_val = (live_price - holding_info.average_cost_price) * holding_info.quantity
                if market_val is not None: holdings_value += market_val
                if unrealized_pnl_val is not None: current_unrealized_pnl += unrealized_pnl_val
            
            holdings_data_list.append(HoldingStatus(
                symbol=symbol_h,
                quantity=holding_info.quantity,
                average_cost_price=holding_info.average_cost_price,
                current_price=live_price,
                market_value=market_val,
                unrealized_pnl=unrealized_pnl_val
            ))

        asset_alloc = {}
        total_portfolio_val_for_alloc = portfolio.cash + holdings_value
        if total_portfolio_val_for_alloc > 0:
            for h_status in holdings_data_list:
                if h_status.market_value is not None:
                     asset_alloc[h_status.symbol] = (h_status.market_value / total_portfolio_val_for_alloc) * 100
            if portfolio.cash > 0:
                 asset_alloc['CASH'] = (portfolio.cash / total_portfolio_val_for_alloc) * 100
        
        portfolio_data_for_response = PortfolioStatusResponse(
            cash=portfolio.cash,
            holdings_value=holdings_value,
            total_value=portfolio.cash + holdings_value,
            realized_pnl=portfolio.realized_pnl,
            unrealized_pnl=current_unrealized_pnl,
            total_pnl=portfolio.realized_pnl + current_unrealized_pnl,
            holdings=holdings_data_list,
            asset_allocation=asset_alloc,
            is_running=is_running_flag 
        )
    # --- End of portfolio_status construction ---

    recent_trades_data = []
    if engine and hasattr(engine, 'get_trade_history'):
        # Assuming TradeRecord has a _asdict() method or similar for Pydantic conversion
        recent_trades_data = [ApiTradeRecord(**trade._asdict()) if hasattr(trade, '_asdict') else ApiTradeRecord(**vars(trade)) for trade in engine.get_trade_history()[-20:]]

    risk_alerts_data = []
    if engine and hasattr(engine, 'get_risk_alerts'):
        risk_alerts_data = [ApiRiskAlert(**alert.model_dump()) for alert in engine.get_risk_alerts()]

    # Get K-line data for the chart using the aggregator
    current_kline_obj: Optional[AggregatorKLineData] = None 
    if klines_aggregator and strategy_info and strategy_info.parameters:
        chart_target_symbol = strategy_info.parameters.get("symbol")
        if chart_target_symbol:
            try:
                current_kline_obj = klines_aggregator.get_current_kline(chart_target_symbol, chart_interval)
                if current_kline_obj:
                    # Optional: log for debugging
                    # print(f"[API /status] Kline for {chart_target_symbol}@{chart_interval}: T={current_kline_obj.time} C={current_kline_obj.close}")
                    pass # Placeholder for print
            except Exception as e:
                print(f"{LogColors.FAIL}[API /status] Error getting K-line from aggregator: {e}{LogColors.ENDC}")

    return SimulationStatusResponse(
        portfolio_status=portfolio_data_for_response,
        recent_trades=recent_trades_data,
        active_strategy=strategy_info,
        is_simulation_running=is_running_flag,
        risk_alerts=risk_alerts_data,
        run_id=current_run_id,
        current_kline_for_chart=current_kline_obj # Use the retrieved K-line object
    )

# --- New API Endpoints for Simulation Control ---

@app.get("/api/simulation/available_strategies", response_model=List[AvailableStrategy])
async def get_available_strategies():
    """Returns a list of strategies available for real-time simulation."""
    return list(STRATEGY_REGISTRY.values())

@app.post("/api/simulation/start", status_code=200)
async def start_simulation(request: StartSimulationRequest):
    global simulation_components

    if simulation_components["running"]:
        raise HTTPException(status_code=400, detail="A simulation is already running. Please stop it before starting a new one.")
        
    # --- Force clear any existing state before starting NEW simulation --- 
    print(f"{LogColors.OKBLUE}BACKEND_API: Clearing any existing/restored state before starting a new simulation...{LogColors.ENDC}")
    stop_current_simulation(clear_all_components=True) # Ensure a completely clean slate

    if request.strategy_id not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Strategy with id '{request.strategy_id}' not found.")

    selected_strategy_meta = STRATEGY_REGISTRY[request.strategy_id]
    
    # Validate parameters
    for param_spec in selected_strategy_meta.parameters:
        if param_spec.required and param_spec.name not in request.parameters:
            raise HTTPException(status_code=400, detail=f"Missing required parameter '{param_spec.name}' for strategy '{selected_strategy_meta.name}'.")
        # Basic type checking (can be expanded)
        if param_spec.name in request.parameters:
            value = request.parameters[param_spec.name]
            expected_type_str = param_spec.type
            actual_type = type(value).__name__
            
            type_match = False
            if expected_type_str == "int" and isinstance(value, int): type_match = True
            elif expected_type_str == "float" and isinstance(value, (int, float)): type_match = True # Allow int for float params
            elif expected_type_str == "str" and isinstance(value, str): type_match = True
            elif expected_type_str == "bool" and isinstance(value, bool): type_match = True
            
            if not type_match:
                 raise HTTPException(status_code=400, detail=f"Invalid type for parameter '{param_spec.name}'. Expected {expected_type_str}, got {actual_type}.")

    # Determine initial capital
    effective_initial_capital = request.initial_capital if request.initial_capital is not None else DEFAULT_INITIAL_CAPITAL

    # --- Prepare Risk Parameters ---
    effective_risk_params: Dict[str, float] = {
        'stop_loss_pct': RISK_MAX_UNREALIZED_LOSS_PER_POSITION_PERCENTAGE,
        'max_pos_pct': RISK_MAX_POSITION_SIZE_PERCENTAGE_OF_PORTFOLIO,
        'max_dd_pct': RISK_MAX_ACCOUNT_DRAWDOWN_PERCENTAGE
    }
    if request.risk_parameters:
        # Validate provided risk parameter keys if necessary
        for key in request.risk_parameters.keys():
            if key not in effective_risk_params:
                # Or just ignore unknown keys, or log a warning
                raise HTTPException(status_code=400, detail=f"Unknown risk parameter key: {key}. Allowed keys are 'stop_loss_pct', 'max_pos_pct', 'max_dd_pct'.")
        effective_risk_params.update(request.risk_parameters)

    # --- Generate Run ID and Prepare Save Directory --- 
    current_run_id = str(uuid.uuid4())
    simulation_components["run_id"] = current_run_id # Store the run ID
    save_dir = os.path.join(SIMULATION_RUNS_BASE_DIR, current_run_id)
    try:
        os.makedirs(save_dir, exist_ok=True)
        print(f"{LogColors.OKCYAN}BACKEND_API: Ensured save directory exists: {save_dir}{LogColors.ENDC}")
    except OSError as e:
         print(f"{LogColors.FAIL}BACKEND_API: Error creating save directory {save_dir}: {e}{LogColors.ENDC}")
         # Decide if this is fatal or not. For now, log and continue, saving might fail.
         # raise HTTPException(status_code=500, detail=f"Could not create simulation save directory: {e}")

    # Clean up previous simulation state if any (though "running" check should prevent overlap)
    # stop_current_simulation(clear_all_components=True) # Ensure a clean slate - Moved below run_id generation
    # We should clear AFTER generating new run_id but BEFORE creating new components
    # The running check already prevents starting if running, so explicit stop might be redundant here
    # Let's ensure components are None before creating new ones
    simulation_components["portfolio"] = None
    simulation_components["engine"] = None
    simulation_components["data_provider"] = None
    simulation_components["strategy"] = None
    simulation_components["strategy_info"] = None
    simulation_components["save_task"] = None
    
    # Initialize components
    try:
        if MockPortfolio is None or MockTradingEngine is None:
            raise ImportError("Core simulation components (Portfolio, Engine) are not loaded.")
        # DataProvider import check will be done conditionally below

        simulation_components["portfolio"] = MockPortfolio(initial_cash=effective_initial_capital, verbose=True)
        
        def get_price_for_engine(symbol: str) -> Optional[float]:
            # Ensure data_provider exists and has the method before calling
            data_provider = simulation_components.get("data_provider")
            if data_provider and hasattr(data_provider, 'get_current_price'):
                return data_provider.get_current_price(symbol)
            return None

        simulation_components["engine"] = MockTradingEngine(
            portfolio=simulation_components["portfolio"],
            risk_parameters=effective_risk_params,
            current_price_provider_callback=get_price_for_engine,
            verbose=True
        )

        strategy_instance: Any = None # To hold the instantiated strategy
        # Ensure strategy_symbol_param is taken from validated request parameters
        strategy_symbol_param = request.parameters.get("symbol")
        if not strategy_symbol_param:
            # This should ideally be caught by parameter validation earlier if 'symbol' is always required by strategies
            raise HTTPException(status_code=400, detail="Strategy parameter 'symbol' is missing.")


        if selected_strategy_meta.id == "realtime_simple_ma":
            if RealtimeSimpleMAStrategy is None: raise ImportError("RealtimeSimpleMAStrategy not loaded.")
            strategy_instance = RealtimeSimpleMAStrategy(
                symbol=strategy_symbol_param, 
                short_window=request.parameters.get("short_window", 5),
                long_window=request.parameters.get("long_window", 10),
                signal_callback=simulation_components["engine"].handle_signal_event,
                verbose=True
            )
        elif selected_strategy_meta.id == "realtime_rsi":
            if RealtimeRSIStrategy is None: raise ImportError("RealtimeRSIStrategy not loaded.")
            strategy_instance = RealtimeRSIStrategy(
                symbol=strategy_symbol_param,
                period=request.parameters.get("period", 14),
                overbought_threshold=request.parameters.get("overbought_threshold", 70),
                oversold_threshold=request.parameters.get("oversold_threshold", 30),
                signal_callback=simulation_components["engine"].handle_signal_event,
                verbose=True
            )
        else:
            # This means a strategy is in STRATEGY_REGISTRY but not handled here
            print(f"{LogColors.FAIL}BACKEND_API: Unhandled strategy ID '{selected_strategy_meta.id}' for instantiation.{LogColors.ENDC}")
            raise HTTPException(status_code=501, detail=f"Strategy type '{selected_strategy_meta.id}' instantiation is not implemented in the API.")
        
        simulation_components["strategy"] = strategy_instance
        # Store strategy info for status endpoint
        simulation_components["strategy_info"] = ApiStrategyInfo(name=selected_strategy_meta.name, parameters=request.parameters)


        # --- Instantiate Data Provider (Mock or Yahoo) ---
        print(f"{LogColors.OKCYAN}BACKEND_API: Attempting to instantiate data provider of type: '{request.data_provider_type}' for symbol '{strategy_symbol_param}'{LogColors.ENDC}")

        if request.data_provider_type == "yahoo":
            if YahooFinanceDataProvider is None:
                print(f"{LogColors.FAIL}BACKEND_API: YahooFinanceDataProvider is None (not imported?).{LogColors.ENDC}")
                raise ImportError("YahooFinanceDataProvider not loaded. Ensure it is imported correctly.")
            
            polling_interval = request.yahoo_polling_interval if request.yahoo_polling_interval is not None else 60
            print(f"{LogColors.OKBLUE}BACKEND_API: Using YahooFinanceDataProvider for symbol: {strategy_symbol_param} with interval {polling_interval}s{LogColors.ENDC}")
            
            simulation_components["data_provider"] = YahooFinanceDataProvider(
                symbols=[strategy_symbol_param], # Yahoo provider takes a list of symbols
                polling_interval_seconds=polling_interval,
                verbose=True # Or make this configurable
            )
        elif request.data_provider_type == "mock": # Explicitly check for "mock"
            if MockRealtimeDataProvider is None:
                print(f"{LogColors.FAIL}BACKEND_API: MockRealtimeDataProvider is None (not imported?).{LogColors.ENDC}")
                raise ImportError("MockRealtimeDataProvider not loaded. Ensure it is imported correctly.")
            print(f"{LogColors.OKBLUE}BACKEND_API: Using MockRealtimeDataProvider for symbol: {strategy_symbol_param}{LogColors.ENDC}")
            
            # Configuration for MockRealtimeDataProvider
            _mock_initial_price = 100.0 # Default initial price
            _mock_volatility = 0.01    # Default volatility
            _mock_interval = 1.0       # Default interval for mock ticks

            # Customize mock parameters based on strategy type if desired (example)
            if selected_strategy_meta.id == "realtime_simple_ma":
                _mock_volatility = 0.015 
            elif selected_strategy_meta.id == "realtime_rsi":
                _mock_volatility = 0.025

            symbols_config_for_mock_provider = [{
                "symbol": strategy_symbol_param,
                "initial_price": _mock_initial_price,
                "volatility": _mock_volatility,
                "interval_seconds": _mock_interval 
                # "trend" was in old config, but MockRealtimeDataProvider doesn't use it directly
            }]
            simulation_components["data_provider"] = MockRealtimeDataProvider(
                symbols_config=symbols_config_for_mock_provider,
                verbose=True # Or make this configurable
            )
        else:
            # Should not happen if Pydantic model has a default and validation
            print(f"{LogColors.FAIL}BACKEND_API: Unknown data_provider_type: {request.data_provider_type}{LogColors.ENDC}")
            raise HTTPException(status_code=400, detail=f"Invalid data_provider_type: {request.data_provider_type}. Must be 'mock' or 'yahoo'.")

        # --- Start Components ---
        current_data_provider = simulation_components.get("data_provider")
        current_strategy = simulation_components.get("strategy")

        if current_strategy and current_data_provider:
            # Ensure strategy has 'on_data_tick' and 'symbol' attributes
            if hasattr(current_strategy, 'on_data_tick') and hasattr(current_strategy, 'symbol'):
                # Ensure the strategy's symbol matches the data provider's configuration (or is handled by it)
                # For single-symbol strategies, this should be fine.
                if current_strategy.symbol == strategy_symbol_param: # Or symbols_list for provider
                    print(f"{LogColors.OKCYAN}BACKEND_API: Subscribing strategy ({selected_strategy_meta.name} for {current_strategy.symbol}) to data provider.{LogColors.ENDC}")
                    current_data_provider.subscribe(
                        current_strategy.symbol, 
                        current_strategy.on_data_tick 
                    )
                else:
                    print(f"{LogColors.WARNING}BACKEND_API: Strategy symbol '{current_strategy.symbol}' does not match data provider's target symbol '{strategy_symbol_param}'. Subscription might fail or be incorrect.{LogColors.ENDC}")
                    # Attempt to subscribe anyway, provider might handle it or log warning if symbol not configured
                    current_data_provider.subscribe(
                        current_strategy.symbol, 
                        current_strategy.on_data_tick
                    )
            else:
                missing_attrs = []
                if not hasattr(current_strategy, 'on_data_tick'): missing_attrs.append("'on_data_tick'")
                if not hasattr(current_strategy, 'symbol'): missing_attrs.append("'symbol'")
                print(f"{LogColors.WARNING}BACKEND_API: Strategy ({selected_strategy_meta.name}) is missing attributes: {', '.join(missing_attrs)}. Cannot subscribe.{LogColors.ENDC}")
        else:
            if not current_strategy:
                 print(f"{LogColors.WARNING}BACKEND_API: Strategy component not initialized. Skipping subscription.{LogColors.ENDC}")
            if not current_data_provider:
                 print(f"{LogColors.WARNING}BACKEND_API: Data Provider component not initialized. Skipping subscription.{LogColors.ENDC}")
        
        if current_data_provider:
            current_data_provider.start()
            print(f"{LogColors.OKGREEN}BACKEND_API: Data provider started.{LogColors.ENDC}")
        else:
            # This case should ideally be caught by the import errors or instantiation logic above.
            print(f"{LogColors.FAIL}BACKEND_API: Critical error - Data provider component is None before start attempt.{LogColors.ENDC}")
            raise HTTPException(status_code=500, detail="Critical error: Data provider component is None after instantiation attempt.")

        simulation_components["running"] = True
        print(f"{LogColors.OKGREEN}BACKEND_API: Simulation '{current_run_id}' for strategy '{selected_strategy_meta.name}' started with {request.data_provider_type} provider.{LogColors.ENDC}")
        
        # Start periodic saving task
        print(f"{LogColors.OKBLUE}BACKEND_API: Starting periodic save task for run_id {current_run_id}...{LogColors.ENDC}")
        simulation_components["save_task"] = asyncio.create_task(_periodic_save_task(current_run_id))
        
        # --- Initial Save --- 
        print(f"{LogColors.OKBLUE}BACKEND_API: Performing initial state save for run_id {current_run_id}...{LogColors.ENDC}")
        await save_simulation_state(current_run_id)
        
        # Initialize or reset Klines Aggregator before data provider starts generating ticks
        if simulation_components.get("klines_aggregator") is None:
            simulation_components["klines_aggregator"] = RealtimeKlinesAggregator()
            print(f"{LogColors.OKCYAN}[API start_simulation] Initialized RealtimeKlinesAggregator.{LogColors.ENDC}")
        else:
            # Ensure reset_all is called on the existing instance
            if hasattr(simulation_components["klines_aggregator"], 'reset_all'):
                simulation_components["klines_aggregator"].reset_all()
                print(f"{LogColors.OKCYAN}[API start_simulation] Reset existing RealtimeKlinesAggregator.{LogColors.ENDC}")
            else: # Should not happen if initialized correctly
                simulation_components["klines_aggregator"] = RealtimeKlinesAggregator()
                print(f"{LogColors.OKCYAN}[API start_simulation] Re-Initialized RealtimeKlinesAggregator due to missing reset_all.{LogColors.ENDC}")

        return {"message": f"Simulation started for strategy '{selected_strategy_meta.name}' with initial capital {effective_initial_capital:.2f} and risk params: {effective_risk_params}. Run ID: {current_run_id}"}

    except ImportError as e:
        # Log this error server-side as it's a configuration/system issue
        print(f"SERVER ERROR during simulation start: Import error - {e}")
        # Clean up partially initialized components
        stop_current_simulation(clear_all_components=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: Could not load necessary simulation components. Details: {e}")
    except Exception as e:
        # Log this error server-side
        print(f"SERVER ERROR during simulation start: {e}")
        # Clean up partially initialized components
        stop_current_simulation(clear_all_components=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


@app.post("/api/simulation/stop", status_code=200)
async def stop_simulation_api():
    """Stops the currently running real-time simulation, retaining portfolio/engine state.
       A final state save is performed.
    """
    global simulation_components
    if not simulation_components["running"]:
        return {"message": "模拟当前未运行."}
    
    # Stop simulation, keeping components, perform final save
    stop_current_simulation(clear_all_components=False) 
    return {"message": "模拟已停止。最终状态已保存。投资组合和交易记录已保留."}

@app.post("/api/simulation/resume", status_code=200)
async def resume_simulation():
    """Resumes a previously stopped simulation using its saved state."""
    global simulation_components

    if simulation_components["running"]:
        raise HTTPException(status_code=400, detail="Simulation is already running.")

    # Check if we have a valid state to resume from
    portfolio = simulation_components.get("portfolio")
    engine = simulation_components.get("engine")
    run_id = simulation_components.get("run_id")
    strategy_info = simulation_components.get("strategy_info")

    if not all([portfolio, engine, run_id, strategy_info]):
        raise HTTPException(status_code=400, detail="No valid simulation state found to resume, or state is incomplete.")

    print(f"{LogColors.OKCYAN}BACKEND_API: Attempting to resume simulation for run_id: {run_id}...{LogColors.ENDC}")

    try:
        # 1. Recreate Data Provider based on restored strategy info
        #    We need the symbol the strategy was using.
        #    Assume strategy_info.parameters contains the necessary info (like 'symbol')
        params = strategy_info.parameters
        strategy_symbol = params.get("symbol")
        if not strategy_symbol:
             raise ValueError("Restored strategy info is missing the required 'symbol' parameter.")
             
        # Use default config for provider for now, could refine later
        # TODO: Consider saving/restoring provider config if it becomes more complex
        symbols_config_for_provider = [{
            "symbol": strategy_symbol,
            "initial_price": engine.current_price_provider_callback(strategy_symbol) or 100.0, # Try to get last price, fallback
            "volatility": 0.01,
            "trend": 0.0,
            "interval_seconds": 1.0 
        }]
        
        if MockRealtimeDataProvider is None:
             raise ImportError("MockRealtimeDataProvider not loaded.")
        new_data_provider = MockRealtimeDataProvider(
            symbols_config=symbols_config_for_provider,
            verbose=True # Or get from restored state? For now, true.
        )

        # 2. Recreate Strategy Instance
        strategy_id = None # Find the ID based on the name or structure of strategy_info
        # This part is tricky, need a reliable way to map strategy_info back to its class/ID
        # For now, let's check the name against our registry
        restored_strategy_name = strategy_info.name
        for reg_id, reg_meta in STRATEGY_REGISTRY.items():
            if reg_meta.name == restored_strategy_name:
                strategy_id = reg_id
                break
        if not strategy_id:
            raise ValueError(f"Could not determine strategy ID for restored strategy name '{restored_strategy_name}'")
            
        new_strategy = None
        if strategy_id == "realtime_simple_ma":
            if RealtimeSimpleMAStrategy is None: raise ImportError("RealtimeSimpleMAStrategy not loaded.")
            new_strategy = RealtimeSimpleMAStrategy(
                # Recreate using restored parameters
                **params, # Pass all restored params
                signal_callback=engine.handle_signal_event, # Connect to RESTORED engine
                verbose=True
            )
        elif strategy_id == "realtime_rsi":
             if RealtimeRSIStrategy is None: raise ImportError("RealtimeRSIStrategy not loaded.")
             new_strategy = RealtimeRSIStrategy(
                **params,
                signal_callback=engine.handle_signal_event, # Connect to RESTORED engine
                verbose=True
            )
        else:
            raise NotImplementedError(f"Resume logic not implemented for strategy ID: {strategy_id}")

        if new_strategy is None:
             raise RuntimeError("Failed to recreate strategy instance.")

        # 3. Connect Strategy to Data Provider
        new_data_provider.subscribe(
            symbol=strategy_symbol,
            callback_function=new_strategy.on_new_tick
        )

        # 4. Update Engine's Price Callback
        def get_price_for_resumed_engine(symbol: str) -> Optional[float]:
            return new_data_provider.get_current_price(symbol)
        engine.current_price_provider_callback = get_price_for_resumed_engine
        
        # 5. Update Global State
        simulation_components["data_provider"] = new_data_provider
        simulation_components["strategy"] = new_strategy
        # Keep existing portfolio, engine, run_id, strategy_info

        # 6. Start Data Provider
        new_data_provider.start()
        simulation_components["running"] = True
        
        # 7. Restart Periodic Save Task (using the existing run_id)
        print(f"{LogColors.OKBLUE}BACKEND_API: Starting periodic save task for resumed run_id {run_id}...{LogColors.ENDC}")
        simulation_components["save_task"] = asyncio.create_task(_periodic_save_task(run_id))

        print(f"{LogColors.OKGREEN}Simulation for run_id {run_id} resumed successfully.{LogColors.ENDC}")
        return {"message": f"Simulation {run_id} resumed successfully."} 

    except (ImportError, ValueError, NotImplementedError, RuntimeError, Exception) as e:
        print(f"{LogColors.FAIL}BACKEND_API: Error resuming simulation {run_id}: {e}{LogColors.ENDC}")
        # Attempt to clean up partially created components on error
        if simulation_components.get("data_provider") != new_data_provider: # Check if new provider was assigned
             if new_data_provider: new_data_provider.stop()
        simulation_components["data_provider"] = None
        simulation_components["strategy"] = None
        simulation_components["running"] = False
        # Cancel save task if it was somehow created
        save_task = simulation_components.get("save_task")
        if save_task and not save_task.done(): save_task.cancel()
        simulation_components["save_task"] = None
        
        raise HTTPException(status_code=500, detail=f"Failed to resume simulation: {e}")

# Helper function needs to be defined before startup_event uses it
def find_latest_simulation_state_file(base_dir: str) -> Optional[str]:
    latest_file = None
    latest_mtime = 0

    if not os.path.exists(base_dir):
        return None

    for run_id_dir in os.listdir(base_dir):
        run_dir_path = os.path.join(base_dir, run_id_dir)
        if not os.path.isdir(run_dir_path):
            continue

        state_file_path = os.path.join(run_dir_path, SIMULATION_STATE_FILENAME)
        if os.path.exists(state_file_path):
            try:
                mtime = os.path.getmtime(state_file_path)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_file = state_file_path
            except OSError:
                continue # Ignore files we can't get mtime for
    
    return latest_file

@app.get("/api/v1/klines/historical", response_model=List[KLineData])
async def get_historical_klines(
    symbol: str,
    interval: str = Query(default="1m", description="Interval string e.g., 1m, 5m, 1h, 1d"),
    limit: int = Query(default=200, gt=0, le=2000, description="Number of kline items to return"),
    end_time: Optional[int] = Query(None, description="End timestamp in UNIX seconds. If None, current time is used."),
    source: Optional[str] = Query("db_then_yahoo", description="Data source preference: e.g., db_only, db_then_yahoo, force_yahoo")
):
    if interval not in ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]:
        # Add more validation as needed, or rely on core_engine to handle invalid interval string
        raise HTTPException(status_code=400, detail=f"Invalid interval: {interval}. Supported intervals are 1m, 5m, etc.")
    
    try:
        # Pass the 'source' parameter to the core fetching logic
        klines = await fetch_historical_klines_core(
            symbol=symbol, 
            interval_str=interval, 
            limit=limit, 
            end_time_ts=end_time,
            source_preference=source # Pass it here
        )
        if not klines:
            # Return empty list if no data, or a 404 if preferred
            # raise HTTPException(status_code=404, detail="No kline data found for the given parameters")
            return []
        return [KLineData(**kline) for kline in klines]
    except ValueError as ve:
        # Handle specific errors from core_engine if they are custom exceptions
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        # Generic error handler for unexpected issues
        print(f"[API Error] get_historical_klines failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching kline data")

@app.get("/api/simulation/trades/{run_id}", response_model=List[ApiTradeRecord])
async def get_all_trades_for_run(run_id: str):
    """Fetches all trade records for a given simulation run_id from its saved state."""
    state_file_path = os.path.join(SIMULATION_RUNS_BASE_DIR, run_id, SIMULATION_STATE_FILENAME)

    if not os.path.exists(state_file_path):
        raise HTTPException(status_code=404, detail=f"Simulation state file not found for run_id: {run_id}")

    try:
        with open(state_file_path, 'r') as f:
            state_data = json.load(f)
        
        engine_state = state_data.get("engine_state")
        if not engine_state:
            # This case means the structure of the state file is unexpected or corrupt regarding engine_state
            print(f"{LogColors.FAIL}[API /api/simulation/trades] Engine state not found in state file for run_id: {run_id}. File: {state_file_path}{LogColors.ENDC}")
            raise HTTPException(status_code=500, detail=f"Engine state not found or corrupt in state file for run_id: {run_id}")
            
        trade_history_raw = engine_state.get("trade_history")
        if trade_history_raw is None: 
            # If trade_history key exists but is null, or if key doesn't exist (get returns None)
            # This is a valid scenario meaning no trades have occurred or been recorded.
            print(f"{LogColors.OKBLUE}[API /api/simulation/trades] Trade history not found or is null for run_id {run_id}. Returning empty list.{LogColors.ENDC}")
            return [] # Return an empty list as per Pydantic List[ApiTradeRecord]

        # Assuming trade_history_raw is a list of dicts compatible with ApiTradeRecord.
        # Pydantic will validate this on return against `response_model=List[ApiTradeRecord]`.
        return trade_history_raw 
        
    except json.JSONDecodeError:
        print(f"{LogColors.FAIL}[API /api/simulation/trades] Error decoding JSON from state file: {state_file_path}{LogColors.ENDC}")
        raise HTTPException(status_code=500, detail=f"Error reading or parsing simulation state file for run_id: {run_id}")
    except Exception as e:
        print(f"{LogColors.FAIL}[API /api/simulation/trades] Unexpected error for run_id {run_id}: {e}{LogColors.ENDC}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while fetching trades for run_id: {run_id}")

if __name__ == "__main__":
    import uvicorn
    # Ensure RESULTS_DIR and API_RUNS_SUBDIR_NAME are correctly resolved if running directly
    # This direct run might have issues with sys.path if not started from project root.
    # It's better to run with `uvicorn backend.main_api:app --reload` from the project root.
    print(f"Attempting to run API directly. Ensure {MAIN_RESULTS_DIR}/{API_RUNS_SUBDIR_NAME} is creatable.")
    
    # For direct run, manually ensure the base API results directory exists for StaticFiles mounting
    # In a real scenario, `startup_event` handles this when run by Uvicorn properly.
    _api_runs_full_path_for_direct_run = os.path.join(MAIN_RESULTS_DIR, API_RUNS_SUBDIR_NAME)
    if not os.path.exists(_api_runs_full_path_for_direct_run):
        try:
            os.makedirs(_api_runs_full_path_for_direct_run)
            print(f"Manually created API results directory for direct run: {_api_runs_full_path_for_direct_run}")
        except OSError as e:
            print(f"Error creating API results directory for direct run {_api_runs_full_path_for_direct_run}: {e}")

    uvicorn.run(app, host="127.0.0.1", port=8089) 
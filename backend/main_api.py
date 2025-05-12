from fastapi import FastAPI, HTTPException, Request
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
    from strategies.simple_ma_strategy import RealtimeSimpleMAStrategy
    from strategies.realtime_rsi_strategy import RealtimeRSIStrategy # Add import for RSI strategy
    from core_engine.risk_manager import RiskAlert # Import RiskAlert
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
    "save_task": None # Added to store the background save task
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

class SimulationStatusResponse(BaseModel):
    portfolio_status: Optional[PortfolioStatusResponse] = None # Made optional
    recent_trades: List[ApiTradeRecord] = [] # Default to empty list
    active_strategy: Optional[ApiStrategyInfo] = None 
    is_simulation_running: bool # New field to clearly indicate if any simulation is running
    risk_alerts: Optional[List[ApiRiskAlert]] = None # New field for risk alerts
    run_id: Optional[str] = None # Added field to indicate if a resumable run exists

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
async def get_simulation_status():
    global simulation_components
    current_run_id = simulation_components.get("run_id") # Get current run_id

    if not simulation_components.get("portfolio") or not simulation_components.get("engine"): # Removed data_provider check here
        # If essential components are not initialized, return a default "not running" or minimal state
        return SimulationStatusResponse(
            portfolio_status=None, 
            recent_trades=[], 
            active_strategy=simulation_components.get("strategy_info"), # Still show strategy if configured
            is_simulation_running=False, # Explicitly false if components missing
            risk_alerts=None, # No alerts if not running
            run_id=current_run_id # Return run_id even if portfolio/engine are missing (maybe restore failed partially)
        )

    portfolio: MockPortfolio = simulation_components["portfolio"]
    engine: MockTradingEngine = simulation_components["engine"]
    data_provider: MockRealtimeDataProvider = simulation_components["data_provider"]
    
    # Helper to provide current price for portfolio calculations
    def get_current_price_for_portfolio(symbol: str) -> Optional[float]:
        if simulation_components["data_provider"] and hasattr(simulation_components["data_provider"], 'get_current_price'):
            return simulation_components["data_provider"].get_current_price(symbol)
        return None

    # Get detailed holdings from portfolio
    # The get_holdings_with_details method returns a list of dicts.
    # We need to convert them to HoldingStatus Pydantic models.
    detailed_holdings_data = portfolio.get_holdings_with_details(get_current_price_for_portfolio)
    pydantic_holdings_list: List[HoldingStatus] = []
    for h_data in detailed_holdings_data:
        pydantic_holdings_list.append(
            HoldingStatus(
                symbol=h_data['symbol'],
                quantity=h_data['quantity'],
                average_cost_price=h_data['average_cost_price'],
                current_price=h_data.get('current_price'), # .get() for safety if field is missing
                market_value=h_data.get('market_value'),
                unrealized_pnl=h_data.get('unrealized_pnl')
            )
        )

    current_portfolio_status = PortfolioStatusResponse(
        cash=portfolio.get_cash(),
        holdings_value=portfolio.get_holdings_value(get_current_price_for_portfolio),
        total_value=portfolio.get_total_portfolio_value(get_current_price_for_portfolio),
        realized_pnl=portfolio.get_realized_pnl(),
        unrealized_pnl=portfolio.get_unrealized_pnl(get_current_price_for_portfolio),
        total_pnl=portfolio.get_total_pnl(get_current_price_for_portfolio),
        holdings=pydantic_holdings_list,
        asset_allocation=portfolio.get_asset_allocation_percentages(get_current_price_for_portfolio),
        is_running=simulation_components.get("running", False) # Use the running flag from global state
    )

    # Get recent trades from engine
    # Engine's trade_log is a list of TradeRecord (which are dicts)
    # Convert them to ApiTradeRecord Pydantic models.
    api_trades_list: List[ApiTradeRecord] = []
    for trade_rec_dict in engine.get_trade_log(): # Assuming get_trade_log returns a list of dicts
        try:
            # Ensure all fields expected by ApiTradeRecord are present in trade_rec_dict
            # This is a common source of errors if the dict structure doesn't match.
            api_trades_list.append(
                ApiTradeRecord(
                    trade_id=str(trade_rec_dict.get('trade_id', uuid.uuid4())), # Provide default if missing
                    symbol=trade_rec_dict['symbol'],
                    timestamp=trade_rec_dict['timestamp'],
                    type=trade_rec_dict['type'],
                    quantity=trade_rec_dict['quantity'],
                    price=trade_rec_dict['price'],
                    total_value=trade_rec_dict['total_value']
                )
            )
        except KeyError as e:
            print(f"BACKEND_API: KeyError when converting trade record to Pydantic model: {e}. Record: {trade_rec_dict}")
            # Optionally, skip this record or add a placeholder
            continue 
        except Exception as e:
            print(f"BACKEND_API: Unexpected error converting trade record: {e}. Record: {trade_rec_dict}")
            continue

    active_risk_alerts_response = []
    if simulation_components["engine"] and hasattr(simulation_components["engine"], 'get_active_risk_alerts'):
        engine_alerts = simulation_components["engine"].get_active_risk_alerts() # type: List[RiskAlert]
        for alert_nt in engine_alerts:
            active_risk_alerts_response.append(ApiRiskAlert(
                alert_type=alert_nt.alert_type,
                symbol=alert_nt.symbol,
                message=alert_nt.message,
                timestamp=alert_nt.timestamp
            ))

    return SimulationStatusResponse(
        portfolio_status=current_portfolio_status,
        recent_trades=api_trades_list[-20:],  # Return last 20 trades for brevity
        active_strategy=simulation_components.get("strategy_info"),
        is_simulation_running=simulation_components.get("running", False), # Use the running flag
        risk_alerts=active_risk_alerts_response if active_risk_alerts_response else None,
        run_id=current_run_id # Include the run_id in the response
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
        if MockPortfolio is None or MockTradingEngine is None or MockRealtimeDataProvider is None:
            raise ImportError("Core simulation components (Portfolio, Engine, DataProvider) are not loaded.")

        simulation_components["portfolio"] = MockPortfolio(initial_cash=effective_initial_capital, verbose=True)
        
        # Get the current price callback for the engine
        def get_price_for_engine(symbol: str) -> Optional[float]:
            if simulation_components["data_provider"]:
                return simulation_components["data_provider"].get_current_price(symbol)
            return None

        simulation_components["engine"] = MockTradingEngine(
            portfolio=simulation_components["portfolio"],
            risk_parameters=effective_risk_params, # Pass the effective risk parameters
            current_price_provider_callback=get_price_for_engine,
            verbose=True
        )

        # Instantiate the selected strategy
        strategy_symbol_param = request.parameters.get("symbol", "DEFAULT_SYM") # Default if not specified, though MA requires it
        symbols_config_for_provider: List[Dict[str, Any]] # Define type for clarity

        if selected_strategy_meta.id == "realtime_simple_ma":
            if RealtimeSimpleMAStrategy is None: raise ImportError("RealtimeSimpleMAStrategy not loaded.")
            simulation_components["strategy"] = RealtimeSimpleMAStrategy(
                symbol=strategy_symbol_param, 
                short_window=request.parameters.get("short_window", 5),
                long_window=request.parameters.get("long_window", 10),
                signal_callback=simulation_components["engine"].handle_signal_event,
                verbose=True
            )
            symbols_config_for_provider = [{
                "symbol": strategy_symbol_param,
                "initial_price": 100.0,
                "volatility": 0.01,
                "trend": 0.0001, # Trend is used by API but not directly by MockRealtimeDataProvider
                "interval_seconds": 1.0 
            }]

        elif selected_strategy_meta.id == "realtime_rsi":
            if RealtimeRSIStrategy is None: raise ImportError("RealtimeRSIStrategy not loaded.")
            simulation_components["strategy"] = RealtimeRSIStrategy(
                symbol=strategy_symbol_param,
                period=request.parameters.get("period", 14), # Corrected: 'rsi_period' to 'period'
                overbought_threshold=request.parameters.get("overbought_threshold", 70),
                oversold_threshold=request.parameters.get("oversold_threshold", 30),
                signal_callback=simulation_components["engine"].handle_signal_event,
                verbose=True
            )
            symbols_config_for_provider = [{
                "symbol": strategy_symbol_param,
                "initial_price": 100.0,
                "volatility": 0.02,
                "trend": -0.00005, # Trend is used by API but not directly by MockRealtimeDataProvider
                "interval_seconds": 1.0
            }]
        else:
            # This case should ideally be caught by `request.strategy_id not in STRATEGY_REGISTRY`
            # but as a safeguard if registry and implementation diverge:
            raise HTTPException(status_code=500, detail=f"Strategy '{selected_strategy_meta.id}' is registered but not implemented in start_simulation.")

        if simulation_components["strategy"] is None: # Should not happen if above logic is correct
             raise HTTPException(status_code=500, detail="Strategy component could not be initialized.")


        simulation_components["data_provider"] = MockRealtimeDataProvider(
            symbols_config=symbols_config_for_provider, # Now correctly a List[SymbolConfig]
            verbose=True
        )
        # Subscribe the strategy's on_new_tick method to the data provider
        simulation_components["data_provider"].subscribe(
            symbol=strategy_symbol_param, # Pass the symbol the strategy is configured for
            callback_function=simulation_components["strategy"].on_new_tick
        )
        
        # Store strategy info for status API
        simulation_components["strategy_info"] = ApiStrategyInfo(
            name=selected_strategy_meta.name,
            parameters=request.parameters
        )

        # Start the data provider (which runs in its own thread)
        simulation_components["data_provider"].start()
        simulation_components["running"] = True
        
        # --- Start the periodic save task --- 
        print(f"{LogColors.OKBLUE}BACKEND_API: Starting periodic save task for run_id {current_run_id}...{LogColors.ENDC}")
        simulation_components["save_task"] = asyncio.create_task(_periodic_save_task(current_run_id))
        
        # --- Initial Save --- 
        print(f"{LogColors.OKBLUE}BACKEND_API: Performing initial state save for run_id {current_run_id}...{LogColors.ENDC}")
        await save_simulation_state(current_run_id)
        
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
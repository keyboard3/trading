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
# import threading # Not directly needed for now as provider manages its own thread

# --- Import from main.py ---
# Ensure main.py is in PYTHONPATH or adjust path accordingly if needed.
# Assuming main.py is in the parent directory for now, adjust if structure is different
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..')) # Add parent dir to sys.path
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

# --- Global Simulation State Variables ---
# Refactored Global Simulation State
simulation_components: Dict[str, Any] = {
    "portfolio": None,
    "engine": None,
    "data_provider": None,
    "strategy": None,
    "strategy_info": None, # Will store an ApiStrategyInfo instance
    "running": False
}
# Lock for thread-safe access to simulation state if needed later
# simulation_lock = threading.Lock()


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
    holdings: List[HoldingStatus]
    is_running: bool

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

class SimulationStatusResponse(BaseModel):
    portfolio_status: Optional[PortfolioStatusResponse] = None # Made optional
    recent_trades: List[ApiTradeRecord] = [] # Default to empty list
    active_strategy: Optional[ApiStrategyInfo] = None 
    is_simulation_running: bool # New field to clearly indicate if any simulation is running

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

# --- Helper function to stop current simulation ---
def stop_current_simulation(clear_all_components: bool = False):
    global simulation_components
    if simulation_components["running"] or clear_all_components:
        print(f"BACKEND_API: stop_current_simulation called. clear_all_components={clear_all_components}")
        
        active_strategy = simulation_components.get("strategy")
        if active_strategy:
            try:
                print("BACKEND_API: Stopping strategy...")
                active_strategy.stop()
            except Exception as e:
                print(f"BACKEND_API: Error stopping strategy: {e}")
            if clear_all_components: # Only clear if explicitly told to
                simulation_components["strategy"] = None

        active_data_provider = simulation_components.get("data_provider")
        if active_data_provider:
            try:
                print("BACKEND_API: Stopping data provider...")
                active_data_provider.stop()
            except Exception as e:
                print(f"BACKEND_API: Error stopping data provider: {e}")
            if clear_all_components: # Only clear if explicitly told to
                simulation_components["data_provider"] = None
        
        if clear_all_components:
            print("BACKEND_API: Clearing portfolio, engine, and strategy_info.")
            simulation_components["portfolio"] = None
            simulation_components["engine"] = None
            simulation_components["strategy_info"] = None
            print("BACKEND_API: All simulation components cleared.")
        else:
            print("BACKEND_API: Active components (strategy, data_provider) stopped. Portfolio/Engine state retained.")

        simulation_components["running"] = False
        print("BACKEND_API: Simulation marked as not running.")


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
    
    # Mount static files directory for API results
    # This allows accessing files like http://localhost:8000/api_runs/<run_id>/report.txt
    app.mount(API_RESULTS_MOUNT_PATH, 
              StaticFiles(directory=api_runs_full_path), 
              name="api_results_static")
    print(f"Static files mounted from '{api_runs_full_path}' at '{API_RESULTS_MOUNT_PATH}'")

    # --- Initialize and Start Global Simulation --- # REMOVED
    # global simulation_portfolio, simulation_engine, simulation_data_provider, simulation_strategy_A, simulation_running
    # global simulation_strategy_A_info # Add to globals

    # if not all([MockPortfolio, MockTradingEngine, MockRealtimeDataProvider, RealtimeSimpleMAStrategy]):
    #     print("CRITICAL: Simulation components not imported correctly. Simulation will not start.")
    #     return

    # print("Initializing global simulation components...")
    # sim_initial_cash = 50000.00
    # sim_fixed_trade_qty = 20 

    # simulation_portfolio = MockPortfolio(initial_cash=sim_initial_cash)
    # simulation_engine = MockTradingEngine(
    #     portfolio=simulation_portfolio, 
    #     fixed_trade_quantity=sim_fixed_trade_qty, 
    #     verbose=True
    # )
    # sim_provider_config = [
    #     {'symbol': 'SIM_STOCK_A', 'initial_price': 120.0, 'volatility': 0.015, 'interval_seconds': 1.0},
    #     {'symbol': 'SIM_STOCK_B', 'initial_price': 75.0, 'volatility': 0.025, 'interval_seconds': 1.2}
    # ]
    # simulation_data_provider = MockRealtimeDataProvider(symbols_config=sim_provider_config, verbose=False)
    
    # sim_strategy_symbol = 'SIM_STOCK_A'
    # sim_short_window = 6
    # sim_long_window = 15
    # simulation_strategy_A = RealtimeSimpleMAStrategy(
    #     symbol=sim_strategy_symbol,
    #     short_window=sim_short_window,
    #     long_window=sim_long_window,
    #     data_provider=simulation_data_provider,
    #     verbose=True,
    #     signal_callback=simulation_engine.handle_signal_event
    # )
    # # Store strategy info
    # simulation_strategy_A_info = ApiStrategyInfo(
    #     name="RealtimeSimpleMAStrategy",
    #     parameters={
    #         "symbol": sim_strategy_symbol,
    #         "short_window": sim_short_window,
    #         "long_window": sim_long_window
    #     }
    # )

    # print("Starting simulation data provider and strategy...")
    # simulation_data_provider.start()
    # simulation_strategy_A.start()
    # simulation_running = True
    # print("Global simulation started.")
    print("Startup complete. Simulation will be started via API call.")


@app.on_event("shutdown")
async def shutdown_event():
    # global simulation_running, simulation_strategy_A, simulation_data_provider # Old globals
    print("FastAPI application shutdown...")
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

# --- New API Endpoint for Simulation Status ---
@app.get("/api/simulation/status", response_model=SimulationStatusResponse)
async def get_simulation_status():
    # global simulation_portfolio, simulation_engine, simulation_strategy_A_info, simulation_running
    global simulation_components

    # If not running AND portfolio is None, it means no simulation was ever run or it was fully cleared.
    # If not running BUT portfolio exists, it means a simulation was run and then stopped, state should be available.
    if not simulation_components["portfolio"]:
        # This covers: never run, or fully reset/cleared simulation
        return SimulationStatusResponse(
            portfolio_status=None,
            recent_trades=[],
            active_strategy=None,
            is_simulation_running=False # Explicitly false
        )

    portfolio = simulation_components["portfolio"]
    engine = simulation_components["engine"] # Engine should also persist if portfolio does
    strategy_info = simulation_components["strategy_info"] # Persists with portfolio/engine
    is_currently_running = simulation_components["running"] # The true current running state
    
    # Data provider is only relevant if is_currently_running is True for fetching latest prices
    data_provider = simulation_components.get("data_provider") if is_currently_running else None
    
    holdings_list = []
    current_total_holdings_value = 0.0
    for symbol, details in portfolio.get_holdings().items():
        current_price = data_provider.get_current_price(symbol) if data_provider else None
        market_value = None
        unrealized_pnl = None
        if current_price is not None:
            market_value = details['quantity'] * current_price
            current_total_holdings_value += market_value
            unrealized_pnl = market_value - (details['quantity'] * details['average_cost_price'])

        holdings_list.append(HoldingStatus(
            symbol=symbol,
            quantity=details['quantity'],
            average_cost_price=details['average_cost_price'],
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
        ))
    
    # Instead of calling get_holdings_value and get_total_portfolio_value on portfolio,
    # we calculate them here based on current prices from the data provider.
    # This ensures the portfolio status reflects the latest market prices.
    # portfolio.get_current_price_callback = data_provider.get_current_price if data_provider else None
    # holdings_value = portfolio.get_holdings_value() # This would need to be updated for current prices
    # total_value = portfolio.get_total_portfolio_value()
    
    cash = portfolio.cash
    total_value = cash + current_total_holdings_value

    portfolio_status_resp = PortfolioStatusResponse(
        cash=cash,
        holdings_value=current_total_holdings_value, 
        total_value=total_value, 
        holdings=holdings_list,
        is_running=is_currently_running # Reflects the actual running state
    )

    # Get recent trades
    raw_trades = engine.get_trade_log()[-10:] if engine else [] # Handle if engine is None (e.g. after a full clear)
    recent_trades_api = []
    for trade_rec in raw_trades:
        # Assuming trade_rec is a dict-like object (e.g. TradeRecord which is a NamedTuple)
        # or directly a dict if it was converted. Let's assume it has ._asdict() if NamedTuple
        # or is directly subscriptable if it's already a dict.
        if hasattr(trade_rec, '_asdict'): # For NamedTuple
            rec_dict = trade_rec._asdict()
        elif isinstance(trade_rec, dict):
            rec_dict = trade_rec
        else: # Fallback if it's an object with attributes
            rec_dict = {
                "trade_id": getattr(trade_rec, 'trade_id', str(uuid.uuid4())), # Ensure ID if missing
                "symbol": getattr(trade_rec, 'symbol', 'UNKNOWN'),
                "timestamp": getattr(trade_rec, 'timestamp', time.time()),
                "type": getattr(trade_rec, 'type', 'UNKNOWN_TYPE'),
                "quantity": getattr(trade_rec, 'quantity', 0),
                "price": getattr(trade_rec, 'price', 0.0),
                "total_value": getattr(trade_rec, 'total_value', 0.0)
            }
        recent_trades_api.append(ApiTradeRecord(**rec_dict))


    return SimulationStatusResponse(
        portfolio_status=portfolio_status_resp,
        recent_trades=recent_trades_api,
        active_strategy=strategy_info,
        is_simulation_running=is_currently_running # Reflect actual running state
    )

# --- New API Endpoints for Simulation Control ---

@app.get("/api/simulation/available_strategies", response_model=List[AvailableStrategy])
async def get_available_strategies():
    """Returns a list of strategies available for real-time simulation."""
    return list(STRATEGY_REGISTRY.values())

@app.post("/api/simulation/start", status_code=200)
async def start_simulation(request: StartSimulationRequest):
    global simulation_components

    print(f"BACKEND_API: Received /api/simulation/start request: {request.model_dump()}")

    # When starting a new simulation, we always stop and fully clear previous components
    # to ensure a fresh start for portfolio, engine etc.
    if simulation_components["running"] or simulation_components["portfolio"]:
        print("BACKEND_API: Simulation is already running or has a previous state. Stopping and clearing all components before starting new.")
        stop_current_simulation(clear_all_components=True) 

    strategy_details = STRATEGY_REGISTRY.get(request.strategy_id)
    if not strategy_details:
        print(f"BACKEND_API: Strategy ID '{request.strategy_id}' not found in registry.")
        raise HTTPException(status_code=404, detail=f"Strategy '{request.strategy_id}' not found")

    # Validate parameters (basic check for required ones, more advanced validation could be added)
    # For now, assume parameters are mostly correct and let component constructors handle errors.
    strategy_params = request.parameters
    data_provider_symbol = strategy_params.get("symbol") # Crucial for MockRealtimeDataProvider

    if not data_provider_symbol:
        print(f"BACKEND_API: 'symbol' parameter missing in request for strategy {request.strategy_id}. Cannot start data provider.")
        raise HTTPException(status_code=400, detail="'symbol' parameter is required for the strategy and data provider.")

    print(f"BACKEND_API: Preparing to start simulation for strategy '{strategy_details.name}' with symbol '{data_provider_symbol}' and params: {strategy_params}")

    try:
        # 1. Initialize Portfolio
        # Use provided initial capital if available, otherwise use a default
        capital_to_use = request.initial_capital if request.initial_capital is not None else DEFAULT_INITIAL_CAPITAL
        if capital_to_use <= 0: # Double check, though Pydantic model should also enforce gt=0
            raise ValueError("Initial capital must be a positive value.")
            
        portfolio = MockPortfolio(initial_cash=capital_to_use)
        print(f"BACKEND_API: MockPortfolio initialized with {capital_to_use:.2f}.")

        # 2. Initialize Trading Engine
        engine = MockTradingEngine(portfolio=portfolio, fixed_trade_quantity=10, verbose=True) # verbose=True for engine logs
        print(f"BACKEND_API: MockTradingEngine initialized.")

        # 3. Initialize Data Provider
        # The provider needs to be configured with the symbol from the strategy request
        provider_config = [
            {'symbol': data_provider_symbol, 'initial_price': 100.0, 'volatility': 0.01, 'interval_seconds': 1.0}
            # Potentially add other symbols if the strategy or UI supports it, or make initial_price/volatility configurable
        ]
        data_provider = MockRealtimeDataProvider(symbols_config=provider_config, verbose=True) # verbose=True for provider logs
        print(f"BACKEND_API: MockRealtimeDataProvider initialized for symbol '{data_provider_symbol}'.")

        # 4. Initialize Strategy
        # Ensure all required params for strategy constructor are present
        # Add verbose to strategy constructor call to enable its internal logging
        strategy_constructor_params = strategy_params.copy()
        strategy_constructor_params['data_provider'] = data_provider
        strategy_constructor_params['signal_callback'] = engine.handle_signal_event
        strategy_constructor_params['verbose'] = True # Enable strategy internal logging
        
        # Ensure the strategy class is callable
        # Dynamic strategy instantiation based on strategy_id
        strategy_instance = None
        if request.strategy_id == "realtime_simple_ma":
            if not RealtimeSimpleMAStrategy:
                 print("BACKEND_API: CRITICAL - RealtimeSimpleMAStrategy class is not available.")
                 raise HTTPException(status_code=500, detail="MA Strategy class not loaded.")
            strategy_instance = RealtimeSimpleMAStrategy(**strategy_constructor_params)
            print(f"BACKEND_API: {strategy_details.name} (MA) initialized with params: {strategy_constructor_params}. Symbol: {data_provider_symbol}")
        elif request.strategy_id == "realtime_rsi":
            if not RealtimeRSIStrategy:
                 print("BACKEND_API: CRITICAL - RealtimeRSIStrategy class is not available.")
                 raise HTTPException(status_code=500, detail="RSI Strategy class not loaded.")
            # RSI strategy might have different specific parameters than MA
            # We assume strategy_constructor_params contains the correct ones based on STRATEGY_REGISTRY validation by Pydantic
            strategy_instance = RealtimeRSIStrategy(**strategy_constructor_params)
            print(f"BACKEND_API: {strategy_details.name} (RSI) initialized with params: {strategy_constructor_params}. Symbol: {data_provider_symbol}")
        else:
            print(f"BACKEND_API: Unknown strategy_id '{request.strategy_id}' for instantiation.")
            raise HTTPException(status_code=500, detail=f"Strategy class for id '{request.strategy_id}' not found or supported for instantiation.")

        # Store components and info
        simulation_components["portfolio"] = portfolio
        simulation_components["engine"] = engine
        simulation_components["data_provider"] = data_provider
        simulation_components["strategy"] = strategy_instance # Use the dynamically created instance
        simulation_components["strategy_info"] = ApiStrategyInfo(name=strategy_details.name, parameters=strategy_params)
        
        # 5. Start components
        data_provider.start()
        strategy_instance.start() # Strategy subscribes to provider
        simulation_components["running"] = True
        
        print(f"BACKEND_API: Simulation started successfully for strategy '{strategy_details.name}' on symbol '{data_provider_symbol}'. Data provider and strategy are active.")
        return {"message": f"Simulation started for strategy '{strategy_details.name}' with symbol '{data_provider_symbol}'."}

    except ValueError as ve:
        print(f"BACKEND_API: ValueError during simulation setup: {ve}")
        stop_current_simulation() # Clean up partially initialized components
        raise HTTPException(status_code=400, detail=f"Error initializing simulation: {ve}")
    except Exception as e:
        print(f"BACKEND_API: Unexpected error during simulation start: {e}")
        stop_current_simulation() # Clean up
        raise HTTPException(status_code=500, detail=f"Failed to start simulation: {e}")


@app.post("/api/simulation/stop", status_code=200)
async def stop_simulation_api():
    """Stops the currently running real-time simulation, retaining portfolio/engine state."""
    global simulation_components
    if not simulation_components["running"]:
        return {"message": "模拟当前未运行."}
    
    stop_current_simulation(clear_all_components=False) # Standard stop, keeps portfolio/engine
    return {"message": "模拟已停止。投资组合和交易记录已保留."}

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

    uvicorn.run(app, host="127.0.0.1", port=8000) 
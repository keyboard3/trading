from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import shutil
import datetime
import uuid

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
except ImportError as e:
    print(f"Error importing from main.py: {e}")
    print("Please ensure main.py is accessible and does not have top-level execution on import if not intended.")
    # Provide fallback for critical missing parts for basic API functionality if main.py fails to import
    MAIN_STRATEGY_CONFIG = {"ERROR": {"description": "Failed to load STRATEGY_CONFIG from main.py"}}
    MAIN_RESULTS_DIR = "results_fallback" 
    def main_init_db(): print("Warning: main_init_db not loaded.")
    DEFAULT_COMMISSION_RATE = 0.0005
    DEFAULT_MIN_COMMISSION = 5.0
    DEFAULT_INITIAL_CAPITAL = 100000.0
    DEFAULT_SLIPPAGE_PCT = 0.001
    def execute_single_backtest_run(*args, **kwargs): 
        return {"error": "execute_single_backtest_run not loaded due to import error from main.py"}


# Remove the local, simplified STRATEGY_CONFIG
# STRATEGY_CONFIG = { ... } 

app = FastAPI()

# --- Constants for API ---
API_RUNS_SUBDIR_NAME = "api_runs" # Subdirectory within MAIN_RESULTS_DIR for API specific runs
API_RESULTS_MOUNT_PATH = f"/{API_RUNS_SUBDIR_NAME}" # Web path to access these results

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
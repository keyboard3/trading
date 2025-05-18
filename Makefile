# Makefile for Quant Trading Project

# Define paths to executables within the virtual environment
VENV_DIR = venv
PYTHON_EXEC = $(VENV_DIR)/bin/python
UVICORN_EXEC = $(VENV_DIR)/bin/uvicorn
PIP_EXEC = $(VENV_DIR)/bin/pip

.PHONY: help run-api run-backtest-main fetch-data init-db-load-csv install-deps check-venv

help:
	@echo "Available commands:"
	@echo "  make check-venv          - Check if the virtual environment executables are found"
	@echo "  make install-deps        - Install dependencies from requirements.txt using venv pip"
	@echo "  make run-api             - Start the FastAPI backend API server (using venv uvicorn)"
	@echo "  make run-backtest-main   - Run the main batch backtesting script (using venv python)"
	@echo "  make fetch-data          - Run the data fetching script (using venv python)"
	@echo "  make init-db-load-csv    - Run the data loading script (using venv python)"

# Target to check if venv paths are valid
check-venv:
	@if [ ! -f "$(PYTHON_EXEC)" ]; then \
		echo "Error: Python executable not found at $(PYTHON_EXEC)"; \
		echo "Please ensure your virtual environment is named 'venv' and is in the project root,"; \
		echo "or update VENV_DIR in the Makefile."; \
		exit 1; \
	fi
	@echo "Virtual environment Python executable seems to be correctly pathed."

# Target to install dependencies (assuming requirements.txt exists)
install-deps: check-venv
	@echo "Installing dependencies from requirements.txt using $(PIP_EXEC)..."
	$(PIP_EXEC) install -r requirements.txt

run-api: check-venv
	@if [ ! -f "$(UVICORN_EXEC)" ]; then \
		echo "Error: Uvicorn executable not found at $(UVICORN_EXEC)"; \
		echo "Have you installed dependencies (e.g., make install-deps or pip install uvicorn)?"; \
		exit 1; \
	fi
	@echo "Starting FastAPI API server on http://0.0.0.0:8089 (using $(UVICORN_EXEC))..."
	$(UVICORN_EXEC) backend.main_api:app --reload --host 0.0.0.0 --port 8089

run-backtest-main: check-venv
	@echo "Running main batch backtesting script (main.py) (using $(PYTHON_EXEC))..."
	$(PYTHON_EXEC) main.py

fetch-data: check-venv
	@echo "Running data fetching script (core_engine/data_fetcher.py) (using $(PYTHON_EXEC))..."
	$(PYTHON_EXEC) -m core_engine.data_fetcher

fetch-historical-data: check-venv
	@echo "Running data loading script (core_engine/data_loader.py) (using $(PYTHON_EXEC))..."
	$(PYTHON_EXEC) -m core_engine.data_loader

init-db-load-csv: check-venv
	@echo "Running data loading script (core_engine/data_loader.py) (using $(PYTHON_EXEC))..."
	$(PYTHON_EXEC) -m core_engine.data_loader

realtime-backtest: check-venv
	@echo "Running realtime backtesting script (core_engine/realtime_backtest.py) (using $(PYTHON_EXEC))..."
	$(PYTHON_EXEC) main_realtime_test.py

test: check-venv
	@echo "Running portfolio manager script (core_engine/portfolio_manager.py) (using $(PYTHON_EXEC))..."
	$(PYTHON_EXEC) -m core_engine.realtime_data_providers

enter-venv:
	@echo "正在进入虚拟环境..."
	@if [ -d "$(VENV_DIR)" ]; then \
		. $(VENV_DIR)/bin/activate; \
		echo "已成功进入虚拟环境。使用 'deactivate' 命令退出。"; \
		exec $(SHELL); \
	else \
		echo "错误：虚拟环境目录 $(VENV_DIR) 不存在。"; \
		echo "请先创建虚拟环境。"; \
		exit 1; \
	fi
	
# You can add other commands here, like for running tests, linting, etc. 
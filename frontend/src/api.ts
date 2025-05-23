import type {
  SimulationStatusResponse,
  AvailableStrategy,
  StartSimulationRequest,
  // BackendResponseMessage, // This type doesn't exist, use { message: string } inline or create it
  KLineData,
  ApiTradeRecord,
} from './types';

const API_BASE_URL = 'http://localhost:8089'; // Assuming backend runs on port 8089

export async function fetchSimulationStatus(): Promise<SimulationStatusResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/simulation/status`);
    if (!response.ok) {
      // Try to parse error body if available, otherwise use status text
      let errorDetail = `HTTP error! status: ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
            // FastAPI validation errors might be an array of objects
            if (Array.isArray(errorData.detail)) {
                // Provide a type for err if known, or use any
                errorDetail = errorData.detail.map((err: any) => `${err.loc?.join(' -> ') || 'error'}: ${err.msg}`).join('; ');
            } else if (typeof errorData.detail === 'string') {
                errorDetail = errorData.detail;
            }
        }
      } catch (e) {
        // Ignore if error body is not json or other parsing error
      }
      throw new Error(errorDetail);
    }
    const data: SimulationStatusResponse = await response.json();
    return data;
  } catch (error) {
    console.error("Failed to fetch simulation status:", error);
    // Re-throw the error so callers can handle it, or return a default/error state
    // For now, re-throwing to make it clear to the caller that it failed.
    throw error;
  }
} 

// --- New API functions for Strategy Switching ---

export async function fetchAvailableStrategies(): Promise<AvailableStrategy[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/simulation/available_strategies`);
    if (!response.ok) {
      // Basic error handling, can be expanded like fetchSimulationStatus
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data: AvailableStrategy[] = await response.json();
    return data;
  } catch (error) {
    console.error("Failed to fetch available strategies:", error);
    throw error;
  }
}

export async function startSimulation(payload: StartSimulationRequest): Promise<{ message: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/simulation/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    // It's good practice to check response.ok and parse JSON for error details
    // even for POST requests that might return simple messages.
    const responseData = await response.json(); // Try to parse JSON regardless of ok status for now

    if (!response.ok) {
        // Attempt to extract a more specific error message from the JSON response
        const errorMessage = responseData?.detail || responseData?.message || `HTTP error! status: ${response.status}`;
        throw new Error(errorMessage);
    }
    return responseData as { message: string };
  } catch (error) {
    console.error("Failed to start simulation:", error);
    throw error;
  }
}

export async function stopSimulation(): Promise<{ message: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/simulation/stop`, {
      method: 'POST',
      // No body needed for stop
    });
    const responseData = await response.json();

    if (!response.ok) {
        const errorMessage = responseData?.detail || responseData?.message || `HTTP error! status: ${response.status}`;
        throw new Error(errorMessage);
    }
    return responseData as { message: string };
  } catch (error) {
    console.error("Failed to stop simulation:", error);
    throw error;
  }
}

// New function to resume simulation
export async function resumeSimulation(): Promise<{ message: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/simulation/resume`, {
      method: 'POST',
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error resuming simulation' }));
      throw new Error(`Failed to resume simulation: ${response.status} ${response.statusText} - ${errorData.detail}`);
    }
    return await response.json();
  } catch (error) {
    console.error('Error resuming simulation:', error);
    throw error;
  }
}

export async function fetchAllTradesForRun(runId: string): Promise<ApiTradeRecord[]> {
  if (!runId) {
    console.warn("fetchAllTradesForRun called with no runId. Returning empty array.");
    return Promise.resolve([]);
  }
  try {
    const response = await fetch(`${API_BASE_URL}/api/simulation/trades/${runId}`);
    if (!response.ok) {
      let errorDetail = `HTTP error! status: ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
          errorDetail = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
        }
      } catch (e) { /* Ignore if error body is not json */ }
      throw new Error(errorDetail);
    }
    const data: ApiTradeRecord[] = await response.json();
    return data;
  } catch (error) {
    console.error(`Failed to fetch all trades for runId ${runId}:`, error);
    throw error;
  }
}

export async function fetchHistoricalKlines(
  symbol: string, 
  interval: string, 
  limit: number, 
  endTime?: Date // Optional end time
): Promise<KLineData[]> {
  const params = new URLSearchParams({
    symbol,
    interval,
    limit: String(limit),
  });
  if (endTime) {
    // Convert Date to ISO string (UTC). Backend expects UTC or will default to it.
    // The backend API Query param for end_time is Optional[datetime.datetime].
    // FastAPI handles parsing ISO string to datetime.
    params.append('end_time', endTime.toISOString());
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/klines/historical?${params.toString()}`);
    if (!response.ok) {
      // Attempt to parse error details from JSON response
      let errorDetail = `HTTP error! status: ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
          if (typeof errorData.detail === 'string') {
            errorDetail = errorData.detail;
          } else if (Array.isArray(errorData.detail)) { // Handle FastAPI validation errors
            errorDetail = errorData.detail.map((err: any) => `${err.loc?.join('->') || 'error'}: ${err.msg}`).join('; ');
          }
        }
      } catch (e) {
        // Ignore if error body isn't JSON
      }
      throw new Error(errorDetail);
    }
    const data: KLineData[] = await response.json();
    return data;
  } catch (error) {
    console.error("Failed to fetch historical klines:", error);
    throw error; // Re-throw to allow caller handling
  }
} 
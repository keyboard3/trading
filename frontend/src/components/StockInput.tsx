import React from 'react';

interface StockInputProps {
  stockSymbols: string;
  onStockSymbolsChange: (symbols: string) => void;
}

const StockInput: React.FC<StockInputProps> = ({ stockSymbols, onStockSymbolsChange }) => {
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onStockSymbolsChange(event.target.value.toUpperCase());
  };

  return (
    <div className="mb-4">
      <label htmlFor="stock-symbols-input" className="block text-sm font-medium text-gray-700 mb-1">
        股票代码 (以逗号分隔):
      </label>
      <input
        type="text"
        id="stock-symbols-input"
        name="stockSymbols"
        value={stockSymbols}
        onChange={handleChange}
        placeholder="例如: AAPL,MSFT,GOOGL"
        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
      />
    </div>
  );
};

export default StockInput; 
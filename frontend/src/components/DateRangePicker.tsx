import React from 'react';

interface DateRangePickerProps {
  startDate: string;
  endDate: string;
  onStartDateChange: (date: string) => void;
  onEndDateChange: (date: string) => void;
}

const DateRangePicker: React.FC<DateRangePickerProps> = ({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
}) => {
  const handleStartDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onStartDateChange(event.target.value);
  };

  const handleEndDateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onEndDateChange(event.target.value);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
      <div>
        <label htmlFor="start-date-input" className="block text-sm font-medium text-gray-700 mb-1">
          开始日期:
        </label>
        <input
          type="date"
          id="start-date-input"
          name="startDate"
          value={startDate}
          onChange={handleStartDateChange}
          className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
        />
      </div>
      <div>
        <label htmlFor="end-date-input" className="block text-sm font-medium text-gray-700 mb-1">
          结束日期:
        </label>
        <input
          type="date"
          id="end-date-input"
          name="endDate"
          value={endDate}
          onChange={handleEndDateChange}
          min={startDate} // 结束日期不能早于开始日期
          className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
        />
      </div>
    </div>
  );
};

export default DateRangePicker; 
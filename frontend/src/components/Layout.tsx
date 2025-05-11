import React from 'react';
import type { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="flex flex-col min-h-screen bg-gray-100">

      <main className="flex-grow container mx-auto p-4 sm:p-3 lg:p-4">
        {children}
      </main>
    </div>
  );
};

export default Layout; 
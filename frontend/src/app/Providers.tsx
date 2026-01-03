'use client';

import { ReactNode } from 'react';
import { ToastProvider } from '@/contexts/ToastContext';
import { HardwareAlert } from '@/components/HardwareAlert';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <HardwareAlert />
      {children}
    </ToastProvider>
  );
}

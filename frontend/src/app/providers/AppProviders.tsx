import type { PropsWithChildren } from 'react';
import { QueryProvider } from '@/app/providers/QueryProvider';
import { DevSessionProvider } from '@/app/providers/DevSessionProvider';
import { AppearanceProvider } from '@/app/providers/AppearanceProvider';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryProvider>
      <DevSessionProvider>
        <AppearanceProvider>{children}</AppearanceProvider>
      </DevSessionProvider>
    </QueryProvider>
  );
}

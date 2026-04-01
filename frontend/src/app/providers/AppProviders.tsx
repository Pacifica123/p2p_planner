import type { PropsWithChildren } from 'react';
import { QueryProvider } from '@/app/providers/QueryProvider';
import { DevSessionProvider } from '@/app/providers/DevSessionProvider';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryProvider>
      <DevSessionProvider>{children}</DevSessionProvider>
    </QueryProvider>
  );
}

import type { PropsWithChildren } from 'react';
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { env } from '@/shared/config/env';

const STORAGE_KEY = 'p2p-planner.dev-user-id';

interface DevSessionContextValue {
  userId: string;
  setUserId: (next: string) => void;
}

const DevSessionContext = createContext<DevSessionContextValue | undefined>(undefined);

function readStoredUserId() {
  if (typeof window === 'undefined') return env.defaultDevUserId;
  const value = window.localStorage.getItem(STORAGE_KEY)?.trim();
  return value || env.defaultDevUserId;
}

export function resolveDevUserId() {
  return readStoredUserId();
}

export function DevSessionProvider({ children }: PropsWithChildren) {
  const [userId, setUserIdState] = useState(readStoredUserId);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, userId);
  }, [userId]);

  const value = useMemo<DevSessionContextValue>(
    () => ({
      userId,
      setUserId: (next) => setUserIdState(next.trim() || env.defaultDevUserId),
    }),
    [userId],
  );

  return <DevSessionContext.Provider value={value}>{children}</DevSessionContext.Provider>;
}

export function useDevSession() {
  const context = useContext(DevSessionContext);
  if (!context) throw new Error('useDevSession must be used inside DevSessionProvider');
  return context;
}

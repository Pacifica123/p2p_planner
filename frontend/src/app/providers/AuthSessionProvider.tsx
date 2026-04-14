import type { PropsWithChildren } from 'react';
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { clearAccessToken } from '@/shared/api/client';
import { refreshSession, signIn, signOut, signOutAll, signUp } from '@/features/auth/api/auth';
import type { AuthSuccessResponse, AuthUser, SignInRequest, SignUpRequest } from '@/shared/types/api';

interface AuthSessionContextValue {
  status: 'loading' | 'authenticated' | 'anonymous';
  user: AuthUser | null;
  sessionId: string | null;
  deviceId: string | null;
  signInWithPassword: (input: SignInRequest) => Promise<void>;
  signUpWithPassword: (input: SignUpRequest) => Promise<void>;
  signOutCurrent: () => Promise<void>;
  signOutEverywhere: () => Promise<void>;
  refreshCurrentSession: () => Promise<void>;
}

const AuthSessionContext = createContext<AuthSessionContextValue | undefined>(undefined);

function toUserState(response: AuthSuccessResponse) {
  return {
    status: 'authenticated' as const,
    user: response.user,
    sessionId: response.sessionId,
    deviceId: response.deviceId,
  };
}

export function AuthSessionProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<'loading' | 'authenticated' | 'anonymous'>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [deviceId, setDeviceId] = useState<string | null>(null);

  const clearLocalSession = () => {
    clearAccessToken();
    setStatus('anonymous');
    setUser(null);
    setSessionId(null);
    setDeviceId(null);
    queryClient.clear();
  };

  const applyAuthResponse = (response: AuthSuccessResponse) => {
    const next = toUserState(response);
    setStatus(next.status);
    setUser(next.user);
    setSessionId(next.sessionId);
    setDeviceId(next.deviceId);
  };

  useEffect(() => {
    let cancelled = false;

    void refreshSession()
      .then((response) => {
        if (cancelled) return;
        applyAuthResponse(response);
      })
      .catch(() => {
        if (!cancelled) {
          clearLocalSession();
        }
      });

    return () => {
      cancelled = true;
    };
    // queryClient intentionally omitted from bootstrap effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo<AuthSessionContextValue>(
    () => ({
      status,
      user,
      sessionId,
      deviceId,
      signInWithPassword: async (input) => {
        const response = await signIn(input);
        applyAuthResponse(response);
      },
      signUpWithPassword: async (input) => {
        const response = await signUp(input);
        applyAuthResponse(response);
      },
      signOutCurrent: async () => {
        try {
          await signOut();
        } finally {
          clearLocalSession();
        }
      },
      signOutEverywhere: async () => {
        try {
          await signOutAll();
        } finally {
          clearLocalSession();
        }
      },
      refreshCurrentSession: async () => {
        const response = await refreshSession();
        applyAuthResponse(response);
      },
    }),
    [deviceId, sessionId, status, user],
  );

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession() {
  const context = useContext(AuthSessionContext);
  if (!context) throw new Error('useAuthSession must be used inside AuthSessionProvider');
  return context;
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as apiClient from "../api/client";
import type { User } from "../api/client";

type AuthState = {
  user: User | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const queryClient = useQueryClient();

  // Au chargement : tenter de restaurer la session via le cookie de rafraîchissement.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (await apiClient.refreshSession()) {
        const me = await apiClient.api<User>("/auth/me").catch(() => null);
        if (!cancelled) setUser(me);
      }
      if (!cancelled) setReady(true);
    })();
    apiClient.setSessionLostHandler(() => {
      setUser(null);
      queryClient.clear();
    });
    return () => {
      cancelled = true;
    };
  }, [queryClient]);

  const signIn = useCallback(async (email: string, password: string) => {
    await apiClient.login(email, password);
    const me = await apiClient.api<User>("/auth/me");
    setUser(me);
    return me;
  }, []);

  const signOut = useCallback(async () => {
    await apiClient.logout();
    queryClient.clear();
    setUser(null);
  }, [queryClient]);

  const value = useMemo(() => ({ user, ready, signIn, signOut }), [user, ready, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans <AuthProvider>");
  return ctx;
}

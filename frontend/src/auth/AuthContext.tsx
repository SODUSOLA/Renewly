import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "../api/client";
import type { User } from "../api/types";

interface AuthState {
  user: User | null;
  // True until we know whether a stored token is still valid.
  loading: boolean;
  // Set when the server rejected our token, so the login page can explain why.
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => void;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  timezone?: string;
}

const AuthContext = createContext<AuthState | null>(null);

// Keeps the signed-in user and token for the whole app.
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => tokenStore.get() !== null);
  const [sessionExpired, setSessionExpired] = useState(false);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    // Cached data belongs to the previous user and must not leak to the next one.
    queryClient.clear();
  }, [queryClient]);

  // Any 401 on a signed-in request means the token expired or was revoked.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      signOut();
      setSessionExpired(true);
    });
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  // On first load, trade a stored token for the user's profile.
  useEffect(() => {
    if (!tokenStore.get()) return;
    let cancelled = false;
    api<User>("/auth/me")
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // A 401 is handled by the global handler; other failures just mean "not signed in".
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: { email, password },
      public: true,
    });
    tokenStore.set(access_token);
    setUser(await api<User>("/auth/me"));
    setSessionExpired(false);
  }, []);

  const register = useCallback(
    async (input: RegisterInput) => {
      await api<User>("/auth/register", { method: "POST", body: input, public: true });
      await login(input.email, input.password);
    },
    [login],
  );

  const value = useMemo(
    () => ({ user, loading, sessionExpired, login, register, logout: signOut }),
    [user, loading, sessionExpired, login, register, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

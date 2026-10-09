import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, refreshAccessToken, setUnauthorizedHandler, tokenStore } from "../api/client";
import type { ReminderStyle, User } from "../api/types";

interface AuthState {
  user: User | null;
  // True until we know whether the visitor already has a session.
  loading: boolean;
  // Set when a session ended while the user was signed in, so the login page can say why.
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (changes: ProfileChanges) => Promise<void>;
}

// The settings a user can change about themselves (email is fixed).
export interface ProfileChanges {
  full_name?: string;
  timezone?: string;
  reminder_style?: ReminderStyle;
  report_emails?: boolean;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  timezone?: string;
}

const AuthContext = createContext<AuthState | null>(null);

// Tabs tell each other about sign-outs so one click signs out everywhere on this device.
const CHANNEL = "renewly-auth";

// Keeps the signed-in user for the whole app. The access token is held in memory by the
// API client; the long-lived refresh token is an HttpOnly cookie this code never sees.
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const channel = useRef<BroadcastChannel | null>(null);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    // Cached data belongs to the previous user and must not leak to the next one.
    queryClient.clear();
  }, [queryClient]);

  // The API client calls this when a session can no longer be renewed.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      signOut();
      setSessionExpired(true);
    });
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  // Another tab signed out.
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const bc = new BroadcastChannel(CHANNEL);
    channel.current = bc;
    bc.onmessage = (event) => {
      if (event.data === "logout") signOut();
    };
    return () => {
      bc.close();
      channel.current = null;
    };
  }, [signOut]);

  // On first load, ask for a session: if the browser holds a valid refresh cookie we get
  // an access token and the profile; otherwise the visitor is simply signed out (no banner).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (await refreshAccessToken()) {
          const me = await api<User>("/auth/me");
          if (!cancelled) setUser(me);
        }
      } catch {
        // Network or server trouble: show the sign-in page; signing in will report it.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
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

  const logout = useCallback(async () => {
    try {
      // Revokes the session on the server and deletes the cookie.
      await api<void>("/auth/logout", { method: "POST", public: true });
    } catch {
      // Even if the server can't be reached, sign out locally.
    }
    signOut();
    channel.current?.postMessage("logout");
  }, [signOut]);

  const updateProfile = useCallback(async (changes: ProfileChanges) => {
    setUser(await api<User>("/auth/me", { method: "PATCH", body: changes }));
  }, []);

  const value = useMemo(
    () => ({ user, loading, sessionExpired, login, register, logout, updateProfile }),
    [user, loading, sessionExpired, login, register, logout, updateProfile],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

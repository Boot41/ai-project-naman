/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";
import api, { clearStoredAuth, readStoredAuth, writeStoredAuth } from "@/lib/api";
import type { AuthState } from "@/types/auth";

interface LoginPayload {
  email: string;
  password: string;
}

interface AuthContextValue extends AuthState {
  login: (payload: LoginPayload) => Promise<{ ok: boolean; message?: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const readAuthFromStorage = (): AuthState => {
  const stored = readStoredAuth();
  if (!stored) {
    return { isAuthenticated: false, userEmail: null, accessToken: null, refreshToken: null };
  }
  return {
    isAuthenticated: true,
    userEmail: stored.user.email,
    accessToken: stored.access_token,
    refreshToken: stored.refresh_token,
  };
};

export function AuthProvider({ children }: PropsWithChildren) {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    userEmail: null,
    accessToken: null,
    refreshToken: null,
  });

  useEffect(() => {
    setAuthState(readAuthFromStorage());
  }, []);

  useEffect(() => {
    const onCleared = () => {
      setAuthState({
        isAuthenticated: false,
        userEmail: null,
        accessToken: null,
        refreshToken: null,
      });
    };
    window.addEventListener("auth:cleared", onCleared);
    return () => window.removeEventListener("auth:cleared", onCleared);
  }, []);

  const login = useCallback(async ({ email, password }: LoginPayload) => {
    try {
      const response = await api.post("/auth/login", {
        username: email.toLowerCase(),
        password,
      });
      writeStoredAuth(response.data);
      const nextState: AuthState = {
        isAuthenticated: true,
        userEmail: response.data.user.email,
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token,
      };
      setAuthState(nextState);
      return { ok: true };
    } catch {
      return { ok: false, message: "Invalid credentials." };
    }
  }, []);

  const logout = useCallback(() => {
    const stored = readStoredAuth();
    if (stored?.refresh_token) {
      void api.post("/auth/logout", { refresh_token: stored.refresh_token }).catch(() => undefined);
    }
    clearStoredAuth();
    setAuthState({ isAuthenticated: false, userEmail: null, accessToken: null, refreshToken: null });
  }, []);

  const value = useMemo(
    () => ({ ...authState, login, logout }),
    [authState, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};

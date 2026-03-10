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
import type { AuthState } from "@/types/auth";

const AUTH_KEY = "opscopilot.auth";
const ALLOWED_EMAIL = "user1@example.com";
const ALLOWED_PASSWORD = "123456";

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
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) {
      return { isAuthenticated: false, userEmail: null };
    }
    const parsed = JSON.parse(raw) as AuthState;
    if (parsed.isAuthenticated && parsed.userEmail) {
      return parsed;
    }
  } catch {
    // Fallback to signed-out state for malformed storage.
  }
  return { isAuthenticated: false, userEmail: null };
};

export function AuthProvider({ children }: PropsWithChildren) {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    userEmail: null,
  });

  useEffect(() => {
    setAuthState(readAuthFromStorage());
  }, []);

  const login = useCallback(async ({ email, password }: LoginPayload) => {
    // TODO: Replace with real authentication API integration.
    await new Promise((resolve) => setTimeout(resolve, 450));

    if (email.toLowerCase() !== ALLOWED_EMAIL || password !== ALLOWED_PASSWORD) {
      return { ok: false, message: "Invalid credentials. Use the provided test account." };
    }

    const nextState: AuthState = {
      isAuthenticated: true,
      userEmail: email.toLowerCase(),
    };

    localStorage.setItem(AUTH_KEY, JSON.stringify(nextState));
    setAuthState(nextState);
    return { ok: true };
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_KEY);
    setAuthState({ isAuthenticated: false, userEmail: null });
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

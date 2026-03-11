import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { LoginResponse } from "@/types/auth";

export const AUTH_KEY = "opscopilot.auth";

type RetryConfig = InternalAxiosRequestConfig & { _retry?: boolean };

export const readStoredAuth = (): LoginResponse | null => {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { isAuthenticated?: boolean } & Partial<LoginResponse>;
    if (!parsed.isAuthenticated || !parsed.access_token || !parsed.refresh_token || !parsed.user) {
      return null;
    }
    return {
      access_token: parsed.access_token,
      refresh_token: parsed.refresh_token,
      token_type: parsed.token_type ?? "bearer",
      expires_in: parsed.expires_in ?? 900,
      user: parsed.user,
    };
  } catch {
    return null;
  }
};

export const writeStoredAuth = (auth: LoginResponse): void => {
  localStorage.setItem(
    AUTH_KEY,
    JSON.stringify({
      isAuthenticated: true,
      userEmail: auth.user.email,
      accessToken: auth.access_token,
      refreshToken: auth.refresh_token,
      ...auth,
    }),
  );
};

export const clearStoredAuth = (): void => {
  localStorage.removeItem(AUTH_KEY);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("auth:cleared"));
  }
};

const api = axios.create({
  baseURL: "/",
  // Wait for long-running investigation responses instead of timing out client-side.
  timeout: 0,
});

api.interceptors.request.use((config) => {
  const stored = readStoredAuth();
  const token = stored?.access_token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const responseStatus = error.response?.status;
    const original = error.config as RetryConfig | undefined;
    if (!original || responseStatus !== 401 || original._retry) {
      return Promise.reject(error);
    }

    const url = original.url ?? "";
    if (url.includes("/auth/login") || url.includes("/auth/refresh") || url.includes("/auth/logout")) {
      return Promise.reject(error);
    }

    original._retry = true;
    clearStoredAuth();
    return Promise.reject(error);
  },
);

export default api;

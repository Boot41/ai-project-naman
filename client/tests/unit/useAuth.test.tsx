import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api, { readStoredAuth } from "@/lib/api";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import type { LoginResponse } from "@/types/auth";

const wrapper = ({ children }: PropsWithChildren) => <AuthProvider>{children}</AuthProvider>;

const loginResponse: LoginResponse = {
  access_token: "acc-1",
  refresh_token: "ref-1",
  token_type: "bearer",
  expires_in: 900,
  user: {
    id: 1,
    username: "ops",
    email: "ops@example.com",
    full_name: "Ops",
    role: "operations_engineer",
  },
};

describe("useAuth", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("logs in via backend and persists tokens", async () => {
    vi.spyOn(api, "post").mockResolvedValueOnce({ data: loginResponse });

    const { result } = renderHook(() => useAuth(), { wrapper });
    const resp = await act(async () =>
      result.current.login({ email: "ops@example.com", password: "secret" }),
    );

    expect(resp.ok).toBe(true);
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));
    expect(result.current.userEmail).toBe("ops@example.com");
    expect(readStoredAuth()?.access_token).toBe("acc-1");
  });

  it("logs out and clears storage", async () => {
    vi.spyOn(api, "post")
      .mockResolvedValueOnce({ data: loginResponse })
      .mockResolvedValueOnce({ data: { success: true } });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login({ email: "ops@example.com", password: "secret" });
    });
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      result.current.logout();
    });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(false));
    expect(readStoredAuth()).toBeNull();
  });
});

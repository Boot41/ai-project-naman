import { afterEach, describe, expect, it } from "vitest";
import { AUTH_KEY, clearStoredAuth, readStoredAuth, writeStoredAuth } from "@/lib/api";
import type { LoginResponse } from "@/types/auth";

const authPayload: LoginResponse = {
  access_token: "access-token",
  refresh_token: "refresh-token",
  token_type: "bearer",
  expires_in: 900,
  user: {
    id: 1,
    username: "ops",
    email: "ops@example.com",
    full_name: "Ops User",
    role: "operations_engineer",
  },
};

describe("api storage helpers", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("writes and reads auth payload", () => {
    writeStoredAuth(authPayload);
    const read = readStoredAuth();
    expect(read).toEqual(authPayload);
  });

  it("returns null for malformed auth storage", () => {
    localStorage.setItem(AUTH_KEY, "{bad_json");
    expect(readStoredAuth()).toBeNull();
  });

  it("clears auth payload", () => {
    writeStoredAuth(authPayload);
    clearStoredAuth();
    expect(localStorage.getItem(AUTH_KEY)).toBeNull();
  });
});

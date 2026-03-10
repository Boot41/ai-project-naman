export interface AuthState {
  isAuthenticated: boolean;
  userEmail: string | null;
  accessToken: string | null;
  refreshToken: string | null;
}

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

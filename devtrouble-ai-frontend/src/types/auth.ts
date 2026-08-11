export type UserRole = 'USER' | 'ADMIN';

export interface User {
  id: string;
  email: string;
  nickname: string;
  role: UserRole;
  created_at: string;
}

export interface SignUpRequest {
  email: string;
  password: string;
  nickname: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

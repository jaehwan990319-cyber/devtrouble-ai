import { apiClient, unwrap } from '../lib/axios';
import type { LoginRequest, SignUpRequest, TokenPair, User } from '../types/auth';

export const authService = {
  async signUp(request: SignUpRequest): Promise<User> {
    const response = await apiClient.post('/auth/signup', request);
    return unwrap<User>(response);
  },

  async login(request: LoginRequest): Promise<TokenPair> {
    const response = await apiClient.post('/auth/login', request);
    return unwrap<TokenPair>(response);
  },

  async logout(refreshToken: string): Promise<void> {
    await apiClient.post('/auth/logout', { refresh_token: refreshToken });
  },

  async getMe(): Promise<User> {
    const response = await apiClient.get('/users/me');
    return unwrap<User>(response);
  },
};

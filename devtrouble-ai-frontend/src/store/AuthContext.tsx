import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { SESSION_EXPIRED_EVENT } from '../lib/axios';
import { tokenStorage } from '../lib/tokenStorage';
import { authService } from '../services/authService';
import type { LoginRequest, SignUpRequest, User } from '../types/auth';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (request: LoginRequest) => Promise<void>;
  signUp: (request: SignUpRequest) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function restoreSession() {
      if (!tokenStorage.getAccessToken()) {
        setIsLoading(false);
        return;
      }
      try {
        const me = await authService.getMe();
        setUser(me);
      } catch {
        tokenStorage.clear();
      } finally {
        setIsLoading(false);
      }
    }
    void restoreSession();
  }, []);

  useEffect(() => {
    // axios 인터셉터가 Refresh Token까지 만료됐다고 판단하면 이 이벤트를 쏜다.
    const handleSessionExpired = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const login = useCallback(async (request: LoginRequest) => {
    const tokens = await authService.login(request);
    tokenStorage.setTokens(tokens.access_token, tokens.refresh_token);
    const me = await authService.getMe();
    setUser(me);
  }, []);

  const signUp = useCallback(
    async (request: SignUpRequest) => {
      await authService.signUp(request);
      await login({ email: request.email, password: request.password });
    },
    [login],
  );

  const logout = useCallback(async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (refreshToken) {
      await authService.logout(refreshToken).catch(() => undefined);
    }
    tokenStorage.clear();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, signUp, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth는 AuthProvider 내부에서만 사용할 수 있습니다.');
  }
  return context;
}

/**
 * Access/Refresh 토큰을 localStorage에 저장/조회하는 단일 진입점.
 *
 * lib/axios.ts(인터셉터)와 store/AuthContext.tsx가 이 모듈을 공유해서
 * "토큰이 어디 저장되는지"에 대한 지식을 한 곳에만 둔다.
 */
const ACCESS_TOKEN_KEY = 'devtrouble.access_token';
const REFRESH_TOKEN_KEY = 'devtrouble.refresh_token';

export const tokenStorage = {
  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

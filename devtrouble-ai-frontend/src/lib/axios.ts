import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { ApiErrorResponse, ApiResponse } from '../types/api';
import { ApiError } from '../types/api';
import { tokenStorage } from './tokenStorage';

/**
 * 개발 환경은 vite.config.ts의 proxy 설정으로 '/api'를 백엔드(localhost:8000)에 전달한다.
 * 운영 환경은 VITE_API_BASE_URL로 실제 API Gateway/ALB 주소를 주입한다.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export const apiClient = axios.create({ baseURL: API_BASE_URL });

/** Refresh Token 재발급 전용 인스턴스. 인터셉터를 타지 않아야 무한 루프를 피할 수 있다. */
const refreshClient = axios.create({ baseURL: API_BASE_URL });

apiClient.interceptors.request.use((config) => {
  const accessToken = tokenStorage.getAccessToken();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

/** 세션이 완전히 만료되었을 때(재발급도 실패) AuthContext가 구독해 전역 로그아웃 처리를 한다. */
export const SESSION_EXPIRED_EVENT = 'devtrouble:session-expired';

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await refreshClient.post<ApiResponse<{ access_token: string; refresh_token: string }>>(
    '/auth/refresh',
    { refresh_token: refreshToken },
  );

  if (!response.data.success) {
    throw new Error(response.data.error.message);
  }

  const { access_token, refresh_token } = response.data.data;
  tokenStorage.setTokens(access_token, refresh_token);
  return access_token;
}

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorResponse>) => {
    const originalConfig = error.config as RetryableConfig | undefined;
    const status = error.response?.status;
    const isRefreshCall = originalConfig?.url?.includes('/auth/refresh');

    if (status === 401 && originalConfig && !originalConfig._retried && !isRefreshCall) {
      originalConfig._retried = true;
      try {
        // 동시에 여러 요청이 401을 맞아도 refresh는 한 번만 수행한다.
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
        const newAccessToken = await refreshPromise;

        originalConfig.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient.request(originalConfig);
      } catch {
        tokenStorage.clear();
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      }
    }

    const errorBody = error.response?.data;
    if (errorBody && !errorBody.success) {
      return Promise.reject(new ApiError(errorBody.error.code, errorBody.error.message, status ?? 0));
    }
    return Promise.reject(new ApiError('NETWORK_ERROR', error.message, status ?? 0));
  },
);

/** ApiResponse<T> 래퍼를 벗기고 실패 시 ApiError를 던지는 헬퍼. services/* 에서 사용. */
export function unwrap<T>(response: { data: ApiResponse<T> }): T {
  if (!response.data.success) {
    throw new ApiError(response.data.error.code, response.data.error.message, 0);
  }
  return response.data.data;
}

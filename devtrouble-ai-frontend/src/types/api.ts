/**
 * 백엔드 표준 응답 포맷과 1:1 매핑.
 * app/schemas/common.py::ApiResponse 참고.
 */
export interface ApiSuccessResponse<T> {
  success: true;
  data: T;
  error: null;
}

export interface ApiErrorResponse {
  success: false;
  data: null;
  error: {
    code: string;
    message: string;
  };
}

export type ApiResponse<T> = ApiSuccessResponse<T> | ApiErrorResponse;

/** axios 인터셉터가 던지는 정규화된 에러. lib/axios.ts 참고. */
export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

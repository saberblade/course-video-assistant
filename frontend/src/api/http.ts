import axios, { AxiosError } from "axios";
import type { ApiErrorBody, ApiErrorShape } from "@/types";

export const http = axios.create({
  baseURL: "/api",
  timeout: 35_000,
});

export class ApiError extends Error {
  code: string;
  requestId?: string;
  retryAfter?: number;
  status?: number;

  constructor(shape: ApiErrorShape) {
    super(shape.message);
    this.name = "ApiError";
    this.code = shape.code;
    this.requestId = shape.requestId;
    this.retryAfter = shape.retryAfter;
    this.status = shape.status;
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiErrorBody>;
    const body = axiosError.response?.data;
    const retryAfter = Number(axiosError.response?.headers?.["retry-after"]);
    if (body?.error) {
      return new ApiError({
        message: body.error.message,
        code: body.error.code,
        requestId: body.request_id,
        retryAfter: Number.isFinite(retryAfter) ? retryAfter : undefined,
        status: axiosError.response?.status,
      });
    }
    if (axiosError.code === "ECONNABORTED") {
      return new ApiError({ code: "REQUEST_TIMEOUT", message: "请求超时，请稍后重试" });
    }
    return new ApiError({
      code: "NETWORK_ERROR",
      message: "无法连接服务，请检查后端是否已启动",
      status: axiosError.response?.status,
    });
  }
  return new ApiError({ code: "UNKNOWN_ERROR", message: "操作未完成，请稍后重试" });
}

export const isMock =
  import.meta.env.VITE_USE_MOCK === "true" ||
  (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK !== "false");

import axios, { AxiosError, CanceledError } from "axios";
import type { ApiErrorBody, ApiErrorShape } from "@/types";
import { clearSession, sessionSignal, sessionState, sessionToken } from "@/stores/session";

declare module "axios" {
  interface AxiosRequestConfig { sessionRevision?: number }
}

export const http = axios.create({
  baseURL: "/api",
  // 必须大于服务端的 LLM_TOTAL_DEADLINE_SECONDS（默认 40s），否则服务端算完、客户端已经先断了。
  timeout: 55_000,
  withCredentials: true,
});

const publicAuth = (url = "") => /^\/auth\/(login|register|me)$/.test(url);
http.interceptors.request.use(config => {
  if (!publicAuth(config.url)) {
    config.sessionRevision = sessionState.revision.value;
    config.signal ??= sessionSignal();
  }
  if (["post", "put", "patch", "delete"].includes(config.method ?? "")) {
    const token = sessionToken();
    if (token) config.headers.set("X-CSRF-Token", token);
  }
  return config;
});
http.interceptors.response.use(response => {
  if (response.config.sessionRevision !== undefined && response.config.sessionRevision !== sessionState.revision.value) {
    throw new CanceledError("账号已切换，请求已取消");
  }
  return response;
}, error => {
  const revision = error.config?.sessionRevision;
  if (revision !== undefined && revision !== sessionState.revision.value) return Promise.reject(new CanceledError("账号已切换，请求已取消"));
  if (error.response?.status === 401 && !publicAuth(error.config?.url)) clearSession("expired", true);
  return Promise.reject(error);
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
  if (axios.isCancel(error)) return new ApiError({ code: "REQUEST_CANCELLED", message: "账号状态已改变，请重新打开页面" });
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
    if (axiosError.response?.status === 403) {
      return new ApiError({ code: "FORBIDDEN", message: "页面校验未通过，请刷新后重试", status: 403 });
    }
    if (axiosError.code === "ECONNABORTED") {
      return new ApiError({ code: "REQUEST_TIMEOUT", message: "请求超时，请稍后重试" });
    }
    return new ApiError({
      code: "NETWORK_ERROR",
      message: "无法连接服务，请稍后重试",
      status: axiosError.response?.status,
    });
  }
  return new ApiError({ code: "UNKNOWN_ERROR", message: "操作未完成，请稍后重试" });
}

export const isMock =
  import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === "true";

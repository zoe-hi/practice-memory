import type { ApiError } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export class RequestError extends Error {
  constructor(public readonly detail: ApiError, public readonly status: number) {
    super(detail.message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: ApiError } | null;
    throw new RequestError(body?.error ?? { code: "NETWORK_ERROR", message: "请求失败，请重试。", retryable: true }, response.status);
  }
  return response.json() as Promise<T>;
}

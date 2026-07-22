const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  constructor({ code = "INTERNAL_ERROR", message = "请求失败", data = {}, status = 0 }) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.data = data;
    this.status = status;
    this.recoverable = Boolean(data?.recoverable);
  }
}

export function apiUrl(path) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function getJson(path, options = {}) {
  return requestJson(path, { ...options, method: "GET" });
}

export async function postJson(path, body, { idempotencyKey, signal } = {}) {
  return requestJson(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
    headers: {
      "Content-Type": "application/json",
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {})
    }
  });
}

async function requestJson(path, options) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      ...options,
      headers: { Accept: "application/json", ...(options.headers || {}) }
    });
  } catch (error) {
    throw new ApiError({
      code: "NETWORK_ERROR",
      message: "无法连接面试服务，请检查服务是否启动",
      data: { recoverable: true, cause: error?.message }
    });
  }

  const payload = await readJson(response);
  if (!response.ok || payload.code !== "OK") {
    throw new ApiError({
      code: payload.code,
      message: payload.message,
      data: payload.data,
      status: response.status
    });
  }
  return payload.data;
}

export async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {
      code: "INVALID_RESPONSE",
      message: "服务返回了无法识别的响应",
      data: { recoverable: true, details: [] }
    };
  }
}

export function newIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

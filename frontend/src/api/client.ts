import type {
  AuditEvent,
  ConversationDetail,
  Meta,
  Overview,
  QueueFilters,
  QueueItem,
  StatusChange,
  TaskOut,
  WinbackItem,
} from "./types";

/** Error with the HTTP status and a message that is safe to show to the user. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!response.ok) {
    // Only the API's own `detail` is shown; anything else (proxy pages, stack traces) is not.
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : `Сервер недоступен (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

function queryString(filters: QueueFilters): string {
  const params = new URLSearchParams();
  for (const key of ["status", "priority", "route", "manager", "player"] as const) {
    for (const value of filters[key] ?? []) params.append(key, value);
  }
  if (filters.overdue !== undefined) params.set("overdue", String(filters.overdue));
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  queue: (filters: QueueFilters) => request<QueueItem[]>(`/api/queue${queryString(filters)}`),
  conversation: (id: string) =>
    request<ConversationDetail>(`/api/conversations/${encodeURIComponent(id)}`),
  updateTask: (taskId: number, change: StatusChange) =>
    request<TaskOut>(`/api/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(change) }),
  audit: (taskId: number) => request<AuditEvent[]>(`/api/tasks/${taskId}/audit`),
  overview: () => request<Overview>("/api/overview"),
  winback: (manager?: string | null) =>
    request<WinbackItem[]>(manager ? `/api/winback?manager=${encodeURIComponent(manager)}` : "/api/winback"),
};

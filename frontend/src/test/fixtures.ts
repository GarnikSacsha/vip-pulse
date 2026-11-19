import type { Meta, Overview, QueueItem } from "../api/types";

export const meta: Meta = {
  as_of: "2026-11-12T13:00:00Z",
  provider: { name: "fake", model: "heuristic-v1", simulated: true, label: "эвристика fake, без модели" },
  counts: {
    total: 9,
    by_status: { open: 5, in_progress: 1, resolved: 1, no_action: 2 },
    by_priority: { P0: 3, P1: 1, P2: 1, P3: 4 },
  },
};

export function queueItem(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    task_id: 1,
    conversation_id: "d-001",
    player: { player_id: "p-001", display_name: "Demo Player 001", manager_id: "mgr-01", segment: "platinum" },
    channel: "telegram",
    status: "open",
    priority: "P0",
    route: "manager",
    category: "withdrawal",
    summary: "Игрок ждёт вывод 5000€ больше суток.",
    next_action: "Проверить статус вывода и сообщить срок.",
    wait_hours: 27,
    awaiting_reply: true,
    overdue: true,
    requires_review: false,
    quality_flags: [],
    reasons: [{ code: "sla.money_critical", text: "Финансовый запрос без ответа 27 ч (порог 24 ч)" }],
    last_message_at: "2026-11-11T10:00:00Z",
    simulated: true,
    ...overrides,
  };
}

/** Numbers of the synthetic sample after triage with the fake provider. */
export const overview: Overview = {
  as_of: "2026-11-12T13:00:00Z",
  totals: {
    total: 9,
    active: 5,
    in_progress: 0,
    critical: 3,
    overdue: 1,
    awaiting_reply: 4,
    escalated: 2,
    quality_issues: 1,
    needs_review: 2,
    resolved: 0,
    no_action: 4,
  },
  managers: [
    { manager_id: "mgr-01", total: 5, active: 3, in_progress: 0, critical: 1, overdue: 1, oldest_wait_hours: 27 },
    { manager_id: "mgr-02", total: 4, active: 2, in_progress: 0, critical: 2, overdue: 0, oldest_wait_hours: 5.75 },
  ],
  categories: [
    { category: "withdrawal", total: 1, active: 1 },
    { category: "other", total: 2, active: 1 },
    { category: "general", total: 1, active: 0 },
  ],
  channels: [
    { channel: "telegram", total: 3, active: 3, overdue: 1 },
    { channel: "email", total: 4, active: 1, overdue: 0 },
  ],
  routes: { manager: 3, rg_specialist: 1, security: 1 },
  coverage: { conversations: 9, in_queue: 9, analysed: 9, failed: 0, simulated: 9 },
};

/** Mocks fetch with a path -> body map; records requested URLs. */
export function serveApi(
  vi: { spyOn: typeof import("vitest").vi.spyOn },
  routes: Record<string, unknown | ((url: string) => unknown)>,
) {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    calls.push(url);
    const path = url.split("?")[0] ?? "";
    const route = routes[path];
    if (route === undefined) return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    const body = typeof route === "function" ? (route as (u: string) => unknown)(url) : route;
    return new Response(JSON.stringify(body), { status: 200 });
  });
  return calls;
}

import type { Meta, QueueItem } from "../api/types";

export const meta: Meta = {
  as_of: "2026-11-12T13:00:00Z",
  provider: { name: "fake", model: "heuristic-v1", simulated: true, label: "эвристика fake, без модели", budget_usd: null, spent_usd: null },
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
    requires_review: false,
    quality_flags: [],
    reasons: [{ code: "sla.money_critical", text: "Финансовый запрос без ответа 27 ч (порог 24 ч)" }],
    last_message_at: "2026-11-11T10:00:00Z",
    simulated: true,
    ...overrides,
  };
}

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

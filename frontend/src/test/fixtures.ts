import type { ConversationDetail, Meta, Overview, QueueItem } from "../api/types";

export const meta: Meta = {
  as_of: "2026-11-12T13:00:00Z",
  provider: { name: "fake", model: "heuristic-v1", simulated: true, label: "эвристика fake, без модели", budget_usd: null, spent_usd: null },
  counts: {
    total: 9,
    by_status: { open: 5, in_progress: 1, resolved: 1, no_action: 2 },
    by_priority: { P0: 3, P1: 1, P2: 1, P3: 4 },
  },
  managers: ["mgr-01", "mgr-02"],
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
    sentiment: "negative",
    summary: "Игрок ждёт вывод 5000€ больше суток.",
    next_action: "Проверить статус вывода и сообщить срок.",
    wait_hours: 27,
    awaiting_reply: true,
    overdue: true,
    sla_hours: 4,
    sla_lane: "breached",
    requires_review: false,
    quality_flags: [],
    manager_errors: [],
    alerts: [],
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
    { manager_id: "mgr-01", total: 5, active: 3, in_progress: 0, critical: 1, overdue: 1, oldest_wait_hours: 27, errors: 2 },
    { manager_id: "mgr-02", total: 4, active: 2, in_progress: 0, critical: 2, overdue: 0, oldest_wait_hours: 5.75, errors: 1 },
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

/** d-001 as the API returns it: two cited messages, one pending. */
export function conversation(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    conversation_id: "d-001",
    channel: "telegram",
    player: {
      player_id: "p-001",
      display_name: "Demo Player 001",
      manager_id: "mgr-01",
      segment: "platinum",
      country: "DE",
      registered_at: "2023-04-11",
    },
    messages: [
      {
        message_id: "m-001-1",
        sender_role: "player",
        sent_at: "2026-11-10T09:00:00Z",
        text: "Вывел 5000€, до сих пор не пришло.",
        is_evidence: true,
        is_pending: false,
      },
      {
        message_id: "m-001-2",
        sender_role: "manager",
        sent_at: "2026-11-10T09:20:00Z",
        text: "Проверю статус и вернусь сегодня.",
        is_evidence: false,
        is_pending: false,
      },
      {
        message_id: "m-001-3",
        sender_role: "player",
        sent_at: "2026-11-11T10:00:00Z",
        text: "Прошли сутки, ответа нет.",
        is_evidence: false,
        is_pending: true,
      },
    ],
    analysis: {
      status: "ok",
      category: "withdrawal",
      sentiment: "negative",
      urgency: "high",
      summary: "Игрок ждёт вывод больше суток, менеджер не вернулся с ответом.",
      confidence: 0.55,
      safety_flag: "none",
      needs_escalation: true,
      manager_errors: [],
      model: "fake:heuristic-v1",
      simulated: true,
      label: "эвристика fake, без модели",
      message: null,
    },
    task: {
      task_id: 1,
      status: "open",
      priority: "P0",
      route: "manager",
      next_action: "Проверить статус вывода у платёжной команды и сообщить игроку срок.",
      reasons: [
        { code: "sla.money_critical", text: "Финансовый запрос без ответа 27 ч (порог 24 ч)" },
        { code: "analysis.escalation", text: "Рекомендована эскалация (эвристика fake, без модели)" },
      ],
      quality_flags: [],
      alerts: [],
      requires_review: false,
      suppress_offers: false,
      updated_at: "2026-11-19T09:00:00Z",
      resolved_at: null,
    },
    facts: {
      as_of: "2026-11-12T13:00:00Z",
      awaiting_reply: true,
      wait_hours: 27,
      response_sla_hours: 4,
      sla_breached: true,
      median_response_minutes: 20,
    },
    ...overrides,
  };
}

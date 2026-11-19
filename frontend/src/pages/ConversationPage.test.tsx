import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import type { AuditEvent, ConversationDetail, TaskStatus } from "../api/types";
import { meta } from "../test/fixtures";

function detail(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    conversation_id: "d-001",
    channel: "telegram",
    player: { player_id: "p-001", display_name: "Demo Player 001", manager_id: "mgr-01", segment: "platinum" },
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

interface Server {
  calls: { url: string; method: string; body: unknown }[];
}

function serve(initial: ConversationDetail, audit: AuditEvent[] = [], patchStatus = 200): Server {
  const server: Server = { calls: [] };
  let current = initial;
  let events = audit;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    server.calls.push({ url, method, body });
    const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
    if (url === "/api/meta") return json(meta);
    if (url === `/api/conversations/${current.conversation_id}`) return json(current);
    if (url.startsWith("/api/conversations/")) return json({ detail: "conversation not found" }, 404);
    if (url.endsWith("/audit")) return json(events);
    if (method === "PATCH") {
      if (patchStatus !== 200) return json({ detail: "cannot move a task from open to open" }, patchStatus);
      const status = (body as { status: TaskStatus }).status;
      if (!current.task) throw new Error("no task");
      current = { ...current, task: { ...current.task, status } };
      events = [
        ...events,
        { at: "2026-11-19T10:00:00Z", actor: "demo-manager", action: "status_changed", before: "open", after: status, note: (body as { note?: string }).note ?? null },
      ];
      return json(current.task);
    }
    return json({ detail: "not found" }, 404);
  });
  return server;
}

function renderPage(id = "d-001") {
  return render(
    <MemoryRouter initialEntries={[`/conversations/${id}`]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("conversation page", () => {
  it("shows the timeline with evidence and pending messages marked", async () => {
    serve(detail());
    renderPage();

    const timeline = await screen.findByRole("list", { name: "Переписка" });
    const items = within(timeline).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Игрок");
    expect(items[0]).toHaveTextContent("Вывел 5000€, до сих пор не пришло.");
    expect(items[0]).toHaveTextContent("Основание вывода");
    expect(items[1]).toHaveTextContent("Менеджер");
    expect(items[1]).not.toHaveTextContent("Основание вывода");
    expect(items[2]).toHaveTextContent("Ждёт ответа");
  });

  it("explains the decision: next step, reasons, analysis and its source", async () => {
    serve(detail());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Demo Player 001" })).toBeInTheDocument();
    expect(screen.getByText("Проверить статус вывода у платёжной команды и сообщить игроку срок.")).toBeInTheDocument();
    const reasons = screen.getByRole("list", { name: "Почему такой приоритет" });
    expect(within(reasons).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Игрок ждёт вывод больше суток, менеджер не вернулся с ответом.")).toBeInTheDocument();
    expect(screen.getByText("Источник: эвристика fake, без модели")).toBeInTheDocument();
    expect(screen.getByText("1 д 3 ч")).toBeInTheDocument();
    expect(screen.getByText("SLA 4 ч нарушен")).toBeInTheDocument();
  });

  it("warns not to offer bonuses in responsible-gaming cases", async () => {
    const base = detail();
    if (!base.task) throw new Error("fixture");
    serve(
      detail({
        task: {
          ...base.task,
          route: "rg_specialist",
          suppress_offers: true,
          requires_review: true,
          quality_flags: ["offer_to_vulnerable_player"],
        },
      }),
    );
    renderPage();

    const warning = await screen.findByRole("note");
    expect(warning).toHaveTextContent("Не предлагать бонусы и акции");
    expect(screen.getByText("Специалист по ответственной игре")).toBeInTheDocument();
    expect(screen.getByText("Бонус уязвимому игроку")).toBeInTheDocument();
  });

  it("changes the task status with a note and shows it in the history", async () => {
    const user = userEvent.setup();
    const server = serve(detail());
    renderPage();

    await screen.findByRole("heading", { name: "Demo Player 001" });
    await user.type(screen.getByLabelText("Комментарий к действию"), "Пишу в платёжный отдел");
    await user.click(screen.getByRole("button", { name: "Взять в работу" }));

    const patch = server.calls.find((c) => c.method === "PATCH");
    expect(patch).toEqual({
      url: "/api/tasks/1",
      method: "PATCH",
      body: { status: "in_progress", actor: "demo-manager", note: "Пишу в платёжный отдел" },
    });
    expect(await screen.findByText("Статус: В работе")).toBeInTheDocument();
    // The history is a separate request that settles after the status: wait for it.
    const history = await screen.findByRole("list", { name: "История" });
    expect(history).toHaveTextContent("Открыта → В работе");
    expect(history).toHaveTextContent("Пишу в платёжный отдел");
    expect(screen.getByLabelText("Комментарий к действию")).toHaveValue("");
  });

  it("offers only the transitions that are allowed", async () => {
    const base = detail();
    if (!base.task) throw new Error("fixture");
    serve(detail({ task: { ...base.task, status: "resolved", resolved_at: "2026-11-19T09:30:00Z" } }));
    renderPage();

    await screen.findByRole("heading", { name: "Demo Player 001" });
    const actions = screen.getByRole("group", { name: "Действия" });
    expect(within(actions).getAllByRole("button").map((b) => b.textContent)).toEqual(["Переоткрыть"]);
  });

  it("shows a rejected status change", async () => {
    const user = userEvent.setup();
    serve(detail(), [], 409);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Отметить решённой" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot move a task from open to open");
  });

  it("says so when the analysis failed instead of inventing a category", async () => {
    serve(
      detail({
        analysis: {
          status: "failed",
          category: null,
          sentiment: null,
          urgency: null,
          summary: null,
          confidence: null,
          safety_flag: null,
          needs_escalation: null,
          model: "gemini:gemini-2.5-flash",
          simulated: false,
          label: "AI",
          message: "Автоматический разбор не выполнен. Проверьте переписку вручную.",
        },
      }),
    );
    renderPage();
    expect(await screen.findByText("Автоматический разбор не выполнен. Проверьте переписку вручную.")).toBeInTheDocument();
    expect(screen.queryByText("Вывод средств")).not.toBeInTheDocument();
  });

  it("handles an unknown conversation", async () => {
    serve(detail());
    renderPage("d-404");
    expect(await screen.findByText("Диалог не найден")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Вернуться в очередь" })).toHaveAttribute("href", "/queue");
  });
});

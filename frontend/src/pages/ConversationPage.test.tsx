import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import type { AuditEvent, ConversationDetail, TaskStatus } from "../api/types";
import { conversation as detail, meta, queueItem } from "../test/fixtures";

// p-001 has two conversations in the sample: the current one and an older, calmer one.
const playerHistory = [
  queueItem({
    player: { player_id: "p-001", display_name: "Demo Player 001", manager_id: "mgr-01", segment: "platinum", country: "DE", registered_at: "2023-04-11" },
  }),
  queueItem({
    task_id: 10,
    conversation_id: "d-010",
    category: "general",
    sentiment: "neutral",
    status: "no_action",
    priority: "P3",
    overdue: false,
    sla_lane: "ok",
    awaiting_reply: false,
    wait_hours: null,
    last_message_at: "2026-10-02T12:00:00Z",
  }),
];

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
    if (url.startsWith("/api/queue?player=")) return json(playerHistory);
    if (url.startsWith("/api/queue")) return json([]);
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
          manager_errors: [],
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

describe("conversation pane: evidence pills", () => {
  it("numbers the cited and pending messages and links them from the analysis", async () => {
    serve(detail());
    renderPage();

    const timeline = await screen.findByRole("list", { name: "Переписка" });
    const items = within(timeline).getAllByRole("listitem");
    expect(within(items[0] as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(within(items[2] as HTMLElement).getByText("2")).toBeInTheDocument();

    const analysis = screen.getByRole("region", { name: "Разбор" });
    expect(within(analysis).getByRole("button", { name: "Сообщение 1: Игрок, 10 ноя, 09:00" })).toBeInTheDocument();
    const facts = screen.getByRole("region", { name: "Факты" });
    expect(within(facts).getByRole("button", { name: "Сообщение 2: Игрок, 11 ноя, 10:00" })).toBeInTheDocument();
  });

  it("highlights the message when its pill is hovered or focused", async () => {
    const user = userEvent.setup();
    serve(detail());
    renderPage();

    const pill = await screen.findByRole("button", { name: /^Сообщение 1:/ });
    const timeline = screen.getByRole("list", { name: "Переписка" });
    const [first] = within(timeline).getAllByRole("listitem");
    expect(first).toHaveAttribute("data-highlighted", "false");

    await user.hover(pill);
    expect(first).toHaveAttribute("data-highlighted", "true");
    await user.unhover(pill);
    expect(first).toHaveAttribute("data-highlighted", "false");

    act(() => pill.focus());
    expect(first).toHaveAttribute("data-highlighted", "true");
  });

  it("highlights the pills that cite a hovered message", async () => {
    const user = userEvent.setup();
    serve(detail());
    renderPage();

    const timeline = await screen.findByRole("list", { name: "Переписка" });
    const [first] = within(timeline).getAllByRole("listitem");
    if (!first) throw new Error("timeline");
    const pill = screen.getByRole("button", { name: /^Сообщение 1:/ });
    expect(pill).toHaveAttribute("data-active", "false");
    await user.hover(first);
    expect(pill).toHaveAttribute("data-active", "true");
  });
});

describe("conversation pane: stand-in output and dossier", () => {
  it("hatches and labels analysis made by the offline stand-in", async () => {
    serve(detail());
    renderPage();
    const analysis = await screen.findByRole("region", { name: "Разбор" });
    expect(analysis).toHaveAttribute("data-simulated", "true");
    expect(within(analysis).getByText("демо")).toBeInTheDocument();
  });

  it("does not hatch analysis made by a model", async () => {
    const base = detail();
    if (!base.analysis) throw new Error("fixture");
    serve(detail({ analysis: { ...base.analysis, simulated: false, label: "AI", model: "gemini:gemini-3.8-flash" } }));
    renderPage();
    const analysis = await screen.findByRole("region", { name: "Разбор" });
    expect(analysis).toHaveAttribute("data-simulated", "false");
    expect(within(analysis).queryByText("демо")).not.toBeInTheDocument();
  });

  it("shows the player dossier with every conversation and the tone trend", async () => {
    const user = userEvent.setup();
    const server = serve(detail());
    renderPage();

    await user.click(await screen.findByRole("tab", { name: "Игрок" }));
    expect(server.calls.map((c) => c.url)).toContain("/api/queue?player=p-001");

    const dossier = await screen.findByRole("tabpanel", { name: "Игрок" });
    expect(dossier).toHaveTextContent("platinum");
    expect(dossier).toHaveTextContent("DE");
    expect(within(dossier).getByRole("img", { name: "Тон игрока по перепискам: нейтральный → негативный" })).toBeInTheDocument();

    const history = within(dossier).getByRole("list", { name: "Переписки игрока" });
    const links = within(history).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/queue/d-001", "/queue/d-010"]);
    expect(links[0]).toHaveAttribute("aria-current", "page");
  });
});

describe("conversation pane: review fixes", () => {
  it("labels stand-in tone in the dossier", async () => {
    const user = userEvent.setup();
    serve(detail());
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Игрок" }));
    const history = await screen.findByRole("list", { name: "Переписки игрока" });
    expect(within(history).getAllByText("демо")).toHaveLength(2);
    expect(screen.getByText(/Оценки тона — демо-эвристика, не модель/)).toBeInTheDocument();
  });

  it("wires both tabs to existing panels and switches them with arrow keys", async () => {
    const user = userEvent.setup();
    serve(detail());
    renderPage();
    const analysisTab = await screen.findByRole("tab", { name: "Разбор" });
    for (const tab of screen.getAllByRole("tab", { name: /Разбор|Игрок/ })) {
      const panel = document.getElementById(tab.getAttribute("aria-controls") ?? "");
      expect(panel).not.toBeNull();
    }
    act(() => analysisTab.focus());
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Игрок" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Игрок" })).toHaveFocus();
  });

  it("keeps a focused pill's highlight when the mouse leaves it", async () => {
    const user = userEvent.setup();
    serve(detail());
    renderPage();
    const pill = await screen.findByRole("button", { name: /^Сообщение 1:/ });
    const [first] = within(screen.getByRole("list", { name: "Переписка" })).getAllByRole("listitem");
    act(() => pill.focus());
    await user.hover(pill);
    await user.unhover(pill);
    expect(first).toHaveAttribute("data-highlighted", "true");
  });
});

describe("conversation pane: manager alerts", () => {
  it("shows a personal-contact notice for a possible second account", async () => {
    const base = detail();
    if (!base.task) throw new Error("fixture");
    serve(detail({ task: { ...base.task, alerts: ["multi_account"] } }));
    renderPage();
    const notice = await screen.findByRole("note", { name: "Уведомление менеджеру" });
    expect(notice).toHaveTextContent("Возможен второй аккаунт или общая карта");
    expect(notice).toHaveTextContent("Свяжитесь с игроком лично");
  });
});


describe("conversation pane: manager mistakes", () => {
  it("shows mistakes found by the analysis with a pill to the message", async () => {
    const base = detail();
    serve({
      ...base,
      messages: base.messages.map((m) => (m.message_id === "m-001-2" ? { ...m, is_evidence: true } : m)),
      analysis: base.analysis && {
        ...base.analysis,
        manager_errors: [{ code: "broken_promise", evidence_message_ids: ["m-001-2"] }],
      },
    });
    renderPage();
    const mistakes = await screen.findByRole("list", { name: "Ошибки менеджера" });
    expect(within(mistakes).getByText("Обещал вернуться и не вернулся")).toBeInTheDocument();
    expect(within(mistakes).getByRole("button", { name: /Сообщение 2/ })).toBeInTheDocument();
  });

  it("highlights the message named in the link", async () => {
    serve(detail());
    render(
      <MemoryRouter initialEntries={["/conversations/d-001?msg=m-001-2"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    const timeline = await screen.findByRole("list", { name: "Переписка" });
    expect(timeline.querySelector("#msg-m-001-2")).toHaveAttribute("data-highlighted", "true");
  });
});

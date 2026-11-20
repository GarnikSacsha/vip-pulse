import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { conversation, meta, queueItem, serveApi } from "../test/fixtures";

const rg = queueItem({
  task_id: 3,
  conversation_id: "d-004",
  player: { player_id: "p-004", display_name: "Demo Player 004", manager_id: "mgr-02", segment: "platinum" },
  category: "responsible_gaming",
  route: "rg_specialist",
  requires_review: true,
  quality_flags: ["offer_to_vulnerable_player"],
  wait_hours: null,
  awaiting_reply: false,
});

function renderQueue(path = "/queue") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

const queueCalls = (calls: string[]) => calls.filter((u) => u.startsWith("/api/queue"));

describe("queue page", () => {
  it("shows active work by default, most urgent first", async () => {
    const calls = serveApi(vi, { "/api/meta": meta, "/api/queue": [queueItem(), rg] });
    renderQueue();

    const rows = await screen.findAllByRole("link", { name: /Demo Player/ });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Demo Player 001");
    expect(queueCalls(calls).at(-1)).toBe("/api/queue?status=open&status=in_progress");

    const [first] = rows;
    if (!first) throw new Error("no rows");
    expect(first).toHaveAttribute("href", "/queue/d-001");
    expect(within(first).getByRole("img", { name: /SLA нарушен/ })).toBeInTheDocument();
    expect(within(first).getByText("P0")).toBeInTheDocument();
    expect(first).toHaveTextContent("Вывод средств · Telegram · platinum");
    expect(within(first).getByText("1 д 3 ч")).toBeInTheDocument();
    expect(within(first).getByText("Проверить статус вывода и сообщить срок.")).toBeInTheDocument();
  });

  it("flags safety routes, review and manager mistakes", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [rg] });
    renderQueue();
    const row = await screen.findByRole("link", { name: /Demo Player 004/ });
    expect(within(row).getByText("Специалист по ответственной игре")).toBeInTheDocument();
    expect(within(row).getByText("Нужна проверка")).toBeInTheDocument();
    expect(within(row).getByText("Бонус уязвимому игроку")).toBeInTheDocument();
    expect(within(row).getByText("ход за игроком")).toBeInTheDocument();
  });

  it("switches views and priority filters through the URL", async () => {
    const user = userEvent.setup();
    const calls = serveApi(vi, { "/api/meta": meta, "/api/queue": [queueItem()] });
    renderQueue();
    await screen.findAllByRole("link", { name: /Demo Player/ });

    await user.click(screen.getByRole("tab", { name: /Все/ }));
    expect(queueCalls(calls).at(-1)).toBe("/api/queue");

    await user.click(screen.getByRole("button", { name: "P0" }));
    expect(queueCalls(calls).at(-1)).toBe("/api/queue?priority=P0");

    await user.click(screen.getByRole("tab", { name: /Решённые/ }));
    expect(queueCalls(calls)).toContain("/api/queue?status=resolved&priority=P0");
  });

  it("opens with filters from a shared link", async () => {
    const calls = serveApi(vi, { "/api/meta": meta, "/api/queue": [] });
    renderQueue("/queue?view=all&priority=P1");
    await screen.findByText(/Нет диалогов/);
    expect(queueCalls(calls).at(-1)).toBe("/api/queue?priority=P1");
    expect(screen.getByRole("tab", { name: /Все/ })).toHaveAttribute("aria-selected", "true");
  });

  it("shows tab counters from meta", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [] });
    renderQueue();
    expect(await screen.findByRole("tab", { name: "Активные 6" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Без действий 2" })).toBeInTheDocument();
  });

  it("explains an empty result", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [] });
    renderQueue();
    expect(await screen.findByText("Нет диалогов по этому фильтру")).toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    const user = userEvent.setup();
    let fail = true;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/meta")) return new Response(JSON.stringify(meta), { status: 200 });
      if (fail) return new Response(JSON.stringify({ detail: "database is locked" }), { status: 500 });
      return new Response(JSON.stringify([queueItem()]), { status: 200 });
    });
    renderQueue();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("database is locked");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Повторить" }));
    expect(await screen.findByRole("link", { name: /Demo Player 001/ })).toBeInTheDocument();
  });
});

describe("queue page: oversight links", () => {
  it("filters by manager from a lead's link and can drop the filter", async () => {
    const user = userEvent.setup();
    const calls = serveApi(vi, { "/api/meta": meta, "/api/queue": [queueItem()] });
    renderQueue("/queue?manager=mgr-01");
    await screen.findAllByRole("link", { name: /Demo Player/ });
    expect(queueCalls(calls)).toContain("/api/queue?status=open&status=in_progress&manager=mgr-01");

    await user.click(screen.getByRole("button", { name: /Менеджер mgr-01/ }));
    expect(queueCalls(calls).at(-1)).toBe("/api/queue?status=open&status=in_progress");
  });

  it("marks overdue items", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [queueItem()] });
    renderQueue();
    const row = await screen.findByRole("link", { name: /Demo Player 001/ });
    expect(within(row).getByText("Просрочено")).toBeInTheDocument();
  });
});

describe("queue page: review fixes", () => {
  it("does not show department-wide counters on a manager's queue", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [queueItem()] });
    renderQueue("/queue?manager=mgr-01");
    await screen.findAllByRole("link", { name: /Demo Player/ });
    // Counted over this manager's items, never the department-wide 6 from meta.
    expect(await screen.findByRole("tab", { name: "Активные 1" })).toBeInTheDocument();
  });

  it("points at the manager filter when it empties the list", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [] });
    renderQueue("/queue?manager=mgr-02");
    expect(await screen.findByText(/фильтр менеджера/)).toBeInTheDocument();
  });

  it("labels stand-in analysis on every row", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [queueItem(), queueItem({ task_id: 2, conversation_id: "d-002", simulated: false })] });
    renderQueue();
    const [demo, model] = await screen.findAllByRole("link", { name: /Demo Player/ });
    if (!demo || !model) throw new Error("rows");
    expect(within(demo).getByText("демо")).toBeInTheDocument();
    expect(within(model).queryByText("демо")).not.toBeInTheDocument();
  });
});

describe("inbox: three panes and keyboard", () => {
  const second = queueItem({
    task_id: 4,
    conversation_id: "d-004",
    player: { player_id: "p-004", display_name: "Demo Player 004", manager_id: "mgr-02", segment: "gold" },
    priority: "P1",
    overdue: false,
    sla_lane: "waiting",
    wait_hours: 1,
  });
  const routes = {
    "/api/meta": meta,
    "/api/queue": [queueItem(), second],
    "/api/conversations/d-001": conversation(),
    "/api/conversations/d-004": conversation({
      conversation_id: "d-004",
      player: { player_id: "p-004", display_name: "Demo Player 004", manager_id: "mgr-02", segment: "gold" },
    }),
  };

  it("asks to pick a conversation until one is selected", async () => {
    serveApi(vi, routes);
    renderQueue();
    await screen.findAllByRole("link", { name: /Demo Player/ });
    expect(screen.getByText("Выберите диалог слева")).toBeInTheDocument();
  });

  it("opens the selected conversation next to the list and keeps the filters", async () => {
    const user = userEvent.setup();
    serveApi(vi, routes);
    renderQueue("/queue?priority=P0");
    const [row] = await screen.findAllByRole("link", { name: /Demo Player 001/ });
    expect(row).toHaveAttribute("href", "/queue/d-001?priority=P0");
    await user.click(row as HTMLElement);

    expect(await screen.findByRole("heading", { name: "Demo Player 001" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Очередь" })).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-current", "page");
  });

  it("moves between conversations with j and k", async () => {
    const user = userEvent.setup();
    serveApi(vi, routes);
    renderQueue();
    await screen.findAllByRole("link", { name: /Demo Player/ });

    await user.keyboard("j");
    expect(await screen.findByRole("heading", { name: "Demo Player 001" })).toBeInTheDocument();
    await user.keyboard("j");
    expect(await screen.findByRole("heading", { name: "Demo Player 004" })).toBeInTheDocument();
    await user.keyboard("j"); // already the last one: stays
    expect(await screen.findByRole("heading", { name: "Demo Player 004" })).toBeInTheDocument();
    await user.keyboard("k");
    expect(await screen.findByRole("heading", { name: "Demo Player 001" })).toBeInTheDocument();
  });

  it("does not steal j and k while the manager types a note", async () => {
    const user = userEvent.setup();
    serveApi(vi, routes);
    renderQueue("/queue/d-001");
    await user.type(await screen.findByLabelText("Комментарий к действию"), "jk");
    expect(screen.getByLabelText("Комментарий к действию")).toHaveValue("jk");
    expect(screen.getByRole("heading", { name: "Demo Player 001" })).toBeInTheDocument();
  });

  it("redirects old conversation links into the inbox", async () => {
    serveApi(vi, routes);
    renderQueue("/conversations/d-004");
    expect(await screen.findByRole("heading", { name: "Demo Player 004" })).toBeInTheDocument();
    const [row] = await screen.findAllByRole("link", { name: /Demo Player 004/ });
    expect(row).toHaveAttribute("aria-current", "page");
  });
});

describe("inbox: review fixes", () => {
  const a = queueItem({ task_id: 1, conversation_id: "d-001" });
  const b = queueItem({
    task_id: 2,
    conversation_id: "d-002",
    player: { player_id: "p-002", display_name: "Demo Player 002", manager_id: "mgr-01", segment: "gold" },
    priority: "P1",
  });
  const c = queueItem({
    task_id: 3,
    conversation_id: "d-003",
    player: { player_id: "p-003", display_name: "Demo Player 003", manager_id: "mgr-02", segment: "gold" },
    priority: "P2",
  });

  it("refreshes the list and the counters after a status change, and j continues from there", async () => {
    const user = userEvent.setup();
    let resolved = false;
    const base = conversation();
    if (!base.task) throw new Error("fixture");
    const calls = serveApi(vi, {
      "/api/meta": meta,
      "/api/queue": () => (resolved ? [a, c] : [a, b, c]),
      "/api/conversations/d-002": conversation({
        conversation_id: "d-002",
        player: b.player,
        task: { ...base.task, task_id: 2 },
      }),
      "/api/conversations/d-003": conversation({ conversation_id: "d-003", player: c.player }),
      "/api/tasks/2": () => {
        resolved = true;
        return { ...base.task, task_id: 2, status: "resolved" };
      },
      "/api/tasks/2/audit": [],
    });
    renderQueue("/queue/d-002");
    await screen.findByRole("heading", { name: "Demo Player 002" });
    const metaBefore = calls.filter((u) => u === "/api/meta").length;

    await user.click(screen.getByRole("button", { name: "Отметить решённой" }));
    await vi.waitFor(() => expect(screen.queryByRole("link", { name: /Demo Player 002/ })).not.toBeInTheDocument());
    expect(calls.filter((u) => u === "/api/meta").length).toBeGreaterThan(metaBefore);

    await user.keyboard("j");
    expect(await screen.findByRole("heading", { name: "Demo Player 003" })).toBeInTheDocument();
  });

  it("keeps the filters and the open tab when the dossier opens another conversation", async () => {
    const user = userEvent.setup();
    serveApi(vi, {
      "/api/meta": meta,
      "/api/queue": (url: string) =>
        url.includes("player=") ? [a, queueItem({ task_id: 10, conversation_id: "d-010", last_message_at: "2026-10-02T12:00:00Z" })] : [a],
      "/api/conversations/d-001": conversation(),
      "/api/conversations/d-010": conversation({ conversation_id: "d-010" }),
    });
    renderQueue("/queue/d-001?priority=P0");
    await user.click(await screen.findByRole("tab", { name: "Игрок" }));
    const history = await screen.findByRole("list", { name: "Переписки игрока" });
    const older = within(history).getAllByRole("link")[1];
    expect(older).toHaveAttribute("href", "/queue/d-010?priority=P0");
    await user.click(older as HTMLElement);
    expect(await screen.findByRole("tabpanel", { name: "Игрок" })).toBeInTheDocument();
  });
});

describe("inbox: manager alerts", () => {
  it("marks conversations where the manager must contact the player personally", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/queue": [queueItem({ alerts: ["multi_account"] })] });
    renderQueue();
    const row = await screen.findByRole("link", { name: /Demo Player 001/ });
    expect(within(row).getByText("Связаться лично")).toBeInTheDocument();
  });
});


describe("queue page: why a long wait is low priority", () => {
  it("says the player's turn or that no answer is needed, and explains the rings", async () => {
    const thanks = queueItem({
      task_id: 30,
      conversation_id: "d-030",
      player: { player_id: "p-030", display_name: "Demo Player 030", manager_id: "mgr-01", segment: "gold" },
      priority: "P3",
      wait_hours: null,
      awaiting_reply: false,
      reply_state: "no_reply_needed",
      overdue: false,
      sla_lane: "ok",
    });
    const theirTurn = queueItem({
      task_id: 31,
      conversation_id: "d-031",
      player: { player_id: "p-031", display_name: "Demo Player 031", manager_id: "mgr-01", segment: "gold" },
      priority: "P2",
      wait_hours: null,
      awaiting_reply: false,
      overdue: false,
      sla_lane: "ok",
    });
    serveApi(vi, { "/api/meta": meta, "/api/queue": [thanks, theirTurn] });
    renderQueue();
    const [first, second] = await screen.findAllByRole("link", { name: /Demo Player 03/ });
    expect(first).toHaveTextContent("не требует ответа (AI)");
    expect(second).toHaveTextContent("ход за игроком");
    expect(screen.getByText(/кольцо заполняется/)).toBeInTheDocument();
  });
});

describe("queue page: small fixes", () => {
  it("says «Действий не требуется» for a low priority without a next step", async () => {
    const quiet = queueItem({ task_id: 50, conversation_id: "d-050", priority: "P3", next_action: null, overdue: false, sla_lane: "ok" });
    serveApi(vi, { "/api/meta": meta, "/api/queue": [quiet] });
    renderQueue();
    const [row] = await screen.findAllByRole("link", { name: /Demo Player 001/ });
    expect(row).toHaveTextContent("Действий не требуется");
  });

  it("counts the tabs over the manager's own players in the manager role", async () => {
    localStorage.setItem("vip-pulse-role", "manager:mgr-01");
    const mine = [
      queueItem(),
      queueItem({ task_id: 51, conversation_id: "d-051", status: "resolved" }),
      queueItem({ task_id: 52, conversation_id: "d-052", status: "no_action" }),
    ];
    serveApi(vi, { "/api/meta": meta, "/api/queue": (url: string) => (url.includes("status=") ? [mine[0]] : mine) });
    renderQueue();
    const tabs = await screen.findAllByRole("tab");
    await screen.findByText("3");
    expect(tabs.map((t) => t.textContent)).toEqual(["Активные 1", "Все 3", "Решённые 1", "Без действий 1"]);
    localStorage.clear();
  });
});

describe("queue page: tab counts follow the priority filter", () => {
  it("counts only P0 items when the P0 filter is on", async () => {
    const p0 = [
      queueItem(),
      queueItem({ task_id: 81, conversation_id: "d-081", status: "resolved" }),
    ];
    const calls = serveApi(vi, { "/api/meta": meta, "/api/queue": (url: string) => (url.includes("status=") ? [p0[0]] : p0) });
    renderQueue("/queue?priority=P0");
    await screen.findByText("2");
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual(["Активные 1", "Все 2", "Решённые 1", "Без действий 0"]);
    expect(calls).toContain("/api/queue?priority=P0");
  });
});

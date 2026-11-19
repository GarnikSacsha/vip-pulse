import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { meta, queueItem, serveApi } from "../test/fixtures";

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
    expect(first).toHaveAttribute("href", "/conversations/d-001");
    expect(within(first).getByText("P0")).toBeInTheDocument();
    expect(within(first).getByText("Вывод средств")).toBeInTheDocument();
    expect(within(first).getByText("Telegram")).toBeInTheDocument();
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
    expect(within(row).getByText("не ждёт")).toBeInTheDocument();
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
    expect(queueCalls(calls).at(-1)).toBe("/api/queue?status=resolved&priority=P0");
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
    expect(queueCalls(calls).at(-1)).toBe("/api/queue?status=open&status=in_progress&manager=mgr-01");

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
    expect(screen.getByRole("tab", { name: "Активные" })).toBeInTheDocument();
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

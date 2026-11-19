import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { meta, overview, queueItem, serveApi } from "../test/fixtures";

const late = queueItem();
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
  overdue: false,
  sla_lane: "ok",
});
const soon = queueItem({
  task_id: 5,
  conversation_id: "d-005",
  player: { player_id: "p-005", display_name: "Demo Player 005", manager_id: "mgr-02", segment: "gold" },
  priority: "P2",
  wait_hours: 3.5,
  overdue: false,
  sla_lane: "at_risk",
});

function renderLead() {
  return render(
    <MemoryRouter initialEntries={["/lead"]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("team lead page", () => {
  it("shows the exceptions as numbers", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late, rg] });
    renderLead();
    expect(await screen.findByRole("heading", { name: "Контроль команды" })).toBeInTheDocument();
    const tiles = within(screen.getByRole("list", { name: "Ключевые показатели" }));
    expect(tiles.getByText("Просрочен ответ").closest("li")).toHaveTextContent("1");
    expect(tiles.getByText("Эскалации").closest("li")).toHaveTextContent("2");
    expect(tiles.getByText("Ошибки менеджеров").closest("li")).toHaveTextContent("1");
  });

  it("lists workload per manager with a link to their queue", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late, rg] });
    renderLead();
    const table = await screen.findByRole("table", { name: "Нагрузка по менеджерам" });
    const row = within(table).getByRole("row", { name: /mgr-01/ });
    expect(within(row).getByRole("link", { name: "mgr-01" })).toHaveAttribute("href", "/queue?manager=mgr-01");
    expect(row).toHaveTextContent("1 д 3 ч"); // oldest wait
  });

  it("groups active items by the reason the lead must look at them", async () => {
    const calls = serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late, rg] });
    renderLead();
    const escalations = await screen.findByRole("region", { name: /Эскалации/ });
    expect(within(escalations).getByRole("link", { name: /Demo Player 004/ })).toHaveAttribute("href", "/queue/d-004");
    expect(within(escalations).queryByText(/Demo Player 001/)).not.toBeInTheDocument();
    const quality = screen.getByRole("region", { name: /Ошибки менеджеров/ });
    expect(within(quality).getByText("Бонус уязвимому игроку")).toBeInTheDocument();

    expect(calls).toContain("/api/queue?status=open&status=in_progress");
  });

  it("says when a group is empty instead of hiding it", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late] });
    renderLead();
    const quality = await screen.findByRole("region", { name: /Ошибки менеджеров/ });
    expect(within(quality).getByText("Нет")).toBeInTheDocument();
  });
});

describe("team lead page: review fixes", () => {
  it("labels stand-in analysis in the exception lists", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late] });
    renderLead();
    const burning = await screen.findByRole("region", { name: /Горит/ });
    expect(within(burning).getByText("демо")).toBeInTheDocument();
  });
});

describe("team lead page: SLA lanes", () => {
  it("sorts active work into lanes decided by the policy", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late, rg, soon] });
    renderLead();
    const board = await screen.findByRole("region", { name: "SLA по активным диалогам" });
    const lane = (name: RegExp) => within(board).getByRole("region", { name });

    const burning = lane(/^Горит/);
    expect(burning).toHaveAccessibleName("Горит · 1");
    expect(within(burning).getByRole("link", { name: /Demo Player 001/ })).toHaveAttribute("href", "/queue/d-001");
    expect(burning).toHaveTextContent("просрочено на 23 ч");
    expect(burning).toHaveTextContent("mgr-01");

    const atRisk = lane(/^Скоро нарушится/);
    expect(within(atRisk).getByText(/Demo Player 005/)).toBeInTheDocument();
    expect(atRisk).toHaveTextContent("осталось 30 мин");

    expect(lane(/^Ждёт/)).toHaveAccessibleName("Ждёт · 0");
    expect(within(lane(/^Всё ок/)).getByText(/Demo Player 004/)).toBeInTheDocument();
  });
});

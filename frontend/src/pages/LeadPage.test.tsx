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
  sla_lane: "specialist",
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
    expect(within(lane(/^У специалиста/)).getByText(/Demo Player 004/)).toBeInTheDocument();
  });
});

describe("team lead page: personal contact", () => {
  it("lists conversations that need the manager to call the player", async () => {
    const multi = queueItem({ task_id: 9, conversation_id: "d-009", alerts: ["multi_account"], overdue: false, sla_lane: "ok" });
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late, multi] });
    renderLead();
    const group = await screen.findByRole("region", { name: /Нужен личный контакт/ });
    expect(within(group).getByRole("link", { name: /Demo Player 001/ })).toHaveAttribute("href", "/queue/d-009");
    expect(within(group).getAllByRole("listitem")).toHaveLength(1);
  });
});


describe("team lead page: lanes and labels agree", () => {
  it("puts escalated work in «У специалиста» and never labels «Всё ок» as running out", async () => {
    const specialist = queueItem({
      task_id: 11,
      conversation_id: "d-011",
      player: { player_id: "p-011", display_name: "Demo Player 011", manager_id: "mgr-02", segment: "gold" },
      route: "rg_specialist",
      category: "responsible_gaming",
      wait_hours: 173,
      overdue: false,
      sla_lane: "specialist",
    });
    const thanks = queueItem({
      task_id: 12,
      conversation_id: "d-012",
      player: { player_id: "p-012", display_name: "Demo Player 012", manager_id: "mgr-01", segment: "gold" },
      priority: "P3",
      wait_hours: 143,
      overdue: false,
      sla_lane: "ok",
    });
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [specialist, thanks] });
    renderLead();
    const board = await screen.findByRole("region", { name: "SLA по активным диалогам" });
    const lane = (name: RegExp) => within(board).getByRole("region", { name });

    const withSpecialist = lane(/^У специалиста/);
    expect(within(withSpecialist).getByText(/Demo Player 011/)).toBeInTheDocument();
    expect(withSpecialist).toHaveTextContent("игрок ждёт 7 д 5 ч");

    const ok = lane(/^Всё ок/);
    expect(within(ok).getByText(/Demo Player 012/)).toBeInTheDocument();
    expect(ok).toHaveTextContent("не ждёт ответа");
    expect(board).not.toHaveTextContent("SLA на исходе");
  });
});

describe("team lead page: manager mistakes", () => {
  it("lists mistakes by manager with their type and a link to the message", async () => {
    const promise = queueItem({
      task_id: 21,
      conversation_id: "d-001",
      status: "resolved",
      manager_errors: [{ code: "broken_promise", evidence_message_ids: ["m-001-2"] }],
    });
    const bonus = queueItem({
      task_id: 22,
      conversation_id: "d-004",
      player: { player_id: "p-004", display_name: "Demo Player 004", manager_id: "mgr-02", segment: "platinum" },
      quality_flags: ["offer_to_vulnerable_player"],
    });
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [promise, bonus] });
    renderLead();
    const panel = await screen.findByRole("region", { name: /Ошибки менеджеров/ });
    const mgr01 = within(panel).getByRole("list", { name: "mgr-01" });
    expect(within(mgr01).getByRole("link", { name: /Обещал вернуться и не вернулся/ })).toHaveAttribute(
      "href",
      "/queue/d-001?msg=m-001-2",
    );
    const mgr02 = within(panel).getByRole("list", { name: "mgr-02" });
    expect(within(mgr02).getByRole("link", { name: /Бонус уязвимому игроку/ })).toHaveAttribute("href", "/queue/d-004");
  });

  it("shows the number of mistakes per manager in the workload table", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview, "/api/queue": [late] });
    renderLead();
    const table = await screen.findByRole("table", { name: "Нагрузка по менеджерам" });
    expect(within(table).getByRole("columnheader", { name: "Ошибки" })).toBeInTheDocument();
    const row = within(table).getByRole("row", { name: /mgr-02/ });
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toContain("1");
  });
});

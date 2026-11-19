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
    const overdue = await screen.findByRole("region", { name: /Просрочен ответ/ });
    expect(within(overdue).getByRole("link", { name: /Demo Player 001/ })).toHaveAttribute(
      "href",
      "/conversations/d-001",
    );
    expect(within(overdue).queryByText(/Demo Player 004/)).not.toBeInTheDocument();

    const escalations = screen.getByRole("region", { name: /Эскалации/ });
    expect(within(escalations).getByText(/Demo Player 004/)).toBeInTheDocument();
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
    const overdue = await screen.findByRole("region", { name: /Просрочен ответ/ });
    expect(within(overdue).getByText("демо")).toBeInTheDocument();
  });
});

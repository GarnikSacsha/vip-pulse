import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { meta, overview, serveApi } from "../test/fixtures";

function renderOverview() {
  return render(
    <MemoryRouter initialEntries={["/overview"]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("head of VIP page", () => {
  it("shows the headline numbers", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview });
    renderOverview();
    expect(await screen.findByRole("heading", { name: "Обзор VIP-отдела" })).toBeInTheDocument();
    const tiles = within(screen.getByRole("list", { name: "Ключевые показатели" }));
    expect(tiles.getByText("Ждут действий").closest("li")).toHaveTextContent("5 из 9");
    expect(tiles.getByText("Критичные").closest("li")).toHaveTextContent("3");
    // 4 players wait for an answer, 1 of them past the SLA.
    const sla = tiles.getByText("Ответ в рамках SLA").closest("li");
    expect(sla).toHaveTextContent("3 из 4 ответят в срок");
    expect(sla).toHaveTextContent("эскалированные к специалисту не входят");
  });

  it("breaks requests down by category and channel", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview });
    renderOverview();
    const categories = await screen.findByRole("table", { name: "Запросы по категориям" });
    const withdrawal = within(categories).getByRole("row", { name: /Вывод средств/ });
    expect(withdrawal).toHaveTextContent("1");
    const channels = screen.getByRole("table", { name: "Каналы" });
    expect(within(channels).getByRole("row", { name: /Email/ })).toHaveTextContent("4");
  });

  it("states where the numbers come from and their limits", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview });
    renderOverview();
    const source = await screen.findByRole("region", { name: "Откуда цифры" });
    expect(source).toHaveTextContent("9 диалогов");
    expect(source).toHaveTextContent("эвристика"); // simulated analysis is never shown as AI
  });

  it("links critical cases to the queue", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/overview": overview });
    renderOverview();
    const link = await screen.findByRole("link", { name: /Открыть критичные/ });
    expect(link).toHaveAttribute("href", "/queue?priority=P0");
  });
});

describe("head of VIP page: where the numbers come from", () => {
  async function source(coverage: Partial<typeof overview.coverage>) {
    serveApi(vi, { "/api/meta": meta, "/api/overview": { ...overview, coverage: { ...overview.coverage, ...coverage } } });
    renderOverview();
    return screen.findByRole("region", { name: "Откуда цифры" });
  }

  it("does not credit the model when every analysis failed", async () => {
    const region = await source({ analysed: 0, failed: 9, simulated: 0 });
    expect(region).toHaveTextContent("Категории не определены");
    expect(region).not.toHaveTextContent("языковая модель");
  });

  it("says how many results are demo when the run is mixed", async () => {
    const region = await source({ analysed: 9, simulated: 3 });
    expect(region).toHaveTextContent("3 из 9");
  });

  it("credits the model only when it produced every result", async () => {
    const region = await source({ analysed: 9, simulated: 0 });
    expect(region).toHaveTextContent("языковая модель");
  });

  it("mentions conversations that are not triaged yet", async () => {
    const region = await source({ conversations: 12, in_queue: 9 });
    expect(region).toHaveTextContent("3 ещё не разобраны");
  });
});

describe("head of VIP page: SLA tile wording", () => {
  it("says so plainly when every waiting player is past the SLA", async () => {
    const allLate = { ...overview, totals: { ...overview.totals, awaiting_reply: 10, overdue: 10 } };
    serveApi(vi, { "/api/meta": meta, "/api/overview": allLate });
    renderOverview();
    const tiles = within(await screen.findByRole("list", { name: "Ключевые показатели" }));
    expect(tiles.getByText("Ответ в рамках SLA").closest("li")).toHaveTextContent("Все 10 ждущих — просрочены");
  });
});

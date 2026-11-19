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
    expect(tiles.getByText("Ответ в рамках SLA").closest("li")).toHaveTextContent("3 из 4");
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

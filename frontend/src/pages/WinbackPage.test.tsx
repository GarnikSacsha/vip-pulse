import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import type { WinbackItem } from "../api/types";
import { meta, serveApi } from "../test/fixtures";

function item(overrides: Partial<WinbackItem> = {}): WinbackItem {
  return {
    player: { player_id: "p-041", display_name: null, manager_id: "mgr-01", segment: "VIP", country: "CIS" },
    tier: "urgent",
    reasons: [
      { code: "winback.silent", text: "Не заходил 25 дн." },
      { code: "winback.stopped_depositing", text: "Перестал вносить депозиты: было $18 000 за 30 дней" },
    ],
    next_action: "Написать лично: спросить, всё ли в порядке.",
    last_login_days: 25,
    last_contact_days: null,
    deposits_30d_usd: 0,
    deposits_prev_30d_usd: 18000,
    favorite_game: "Demo Slot",
    latest_conversation_id: null,
    ...overrides,
  };
}

const intro = item({
  player: { player_id: "p-049", display_name: null, manager_id: "mgr-02", segment: "VIP" },
  tier: "introduce",
  reasons: [{ code: "winback.no_contact", text: "Менеджер ещё не писал игроку" }],
  next_action: "Познакомиться: короткое личное сообщение от менеджера, без промо.",
  last_login_days: 1,
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("win-back page", () => {
  it("is in the main navigation", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/winback": [] });
    renderAt("/winback");
    expect(screen.getByRole("link", { name: "Кого вернуть" })).toHaveAttribute("href", "/winback");
    expect(await screen.findByRole("heading", { name: "Кого вернуть" })).toBeInTheDocument();
  });

  it("groups players by tier with reasons and the next step", async () => {
    const calls = serveApi(vi, { "/api/meta": meta, "/api/winback": [item(), intro] });
    renderAt("/winback");
    const urgent = await screen.findByRole("region", { name: /Вернуть срочно/ });
    expect(urgent).toHaveTextContent("p-041");
    expect(urgent).toHaveTextContent("Не заходил 25 дн.");
    expect(urgent).toHaveTextContent("Написать лично");
    expect(urgent).toHaveTextContent("Переписок ещё не было");
    const introduce = screen.getByRole("region", { name: /Познакомиться/ });
    expect(within(introduce).getByText(/p-049/)).toBeInTheDocument();
    expect(calls).toContain("/api/winback");
  });

  it("links to the latest conversation when there is one", async () => {
    serveApi(vi, { "/api/meta": meta, "/api/winback": [item({ latest_conversation_id: "d-013", last_contact_days: 1 })] });
    renderAt("/winback");
    const link = await screen.findByRole("link", { name: /Открыть переписку/ });
    expect(link).toHaveAttribute("href", "/queue/d-013");
  });

  it("filters by manager from the URL", async () => {
    const calls = serveApi(vi, { "/api/meta": meta, "/api/winback": [] });
    renderAt("/winback?manager=mgr-01");
    expect(await screen.findByText(/Сейчас некого возвращать/)).toBeInTheDocument();
    expect(calls).toContain("/api/winback?manager=mgr-01");
  });
});

describe("win-back page: birthdays and open requests", () => {
  it("lists birthdays near the data date as a reason to write, without promo", async () => {
    const birthdays = [
      { player: { player_id: "p-050", display_name: null, manager_id: "mgr-01", segment: "VIP" }, birthday: "1990-11-14", days: 2, next_action: "Поздравить лично, без бонуса и промо." },
      { player: { player_id: "p-051", display_name: null, manager_id: "mgr-01", segment: "VIP" }, birthday: "1985-11-09", days: -3, next_action: "Поздравить лично, без бонуса и промо." },
    ];
    const calls = serveApi(vi, { "/api/meta": meta, "/api/winback": [], "/api/birthdays": birthdays });
    renderAt("/winback?manager=mgr-01");
    const block = await screen.findByRole("region", { name: /Повод написать: день рождения/ });
    const rows = within(block).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("p-050");
    expect(rows[0]).toHaveTextContent("через 2 дн.");
    expect(rows[1]).toHaveTextContent("3 дн. назад");
    expect(block).toHaveTextContent("Поздравить лично, без бонуса и промо.");
    expect(calls).toContain("/api/birthdays?manager=mgr-01");
  });

  it("sends the manager to the open request before any win-back message", async () => {
    const waiting = item({
      next_action: "Сначала закрыть открытый запрос игрока в очереди, потом писать про возвращение.",
      open_request: { conversation_id: "d-020", category: "withdrawal", priority: "P0", wait_hours: 50 },
    });
    serveApi(vi, { "/api/meta": meta, "/api/winback": [waiting], "/api/birthdays": [] });
    renderAt("/winback");
    const urgent = await screen.findByRole("region", { name: /Вернуть срочно/ });
    const link = within(urgent).getByRole("link", { name: /Сначала закрой открытый запрос: Вывод средств, ждёт 2 д 2 ч/ });
    expect(link).toHaveAttribute("href", "/queue/d-020");
    expect(urgent).not.toHaveTextContent("другое казино");
  });
});

import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { Player, PlayerProfile } from "../api/types";
import { serveApi } from "../test/fixtures";
import { Dossier } from "./Dossier";

const EMPTY: PlayerProfile = {
  account_status: null,
  brand: null,
  language: null,
  geo: null,
  deposits_30d_usd: null,
  deposits_30d_count: null,
  deposits_prev_30d_usd: null,
  deposits_prev_30d_count: null,
  last_deposit_at: null,
  failed_deposits_7d: null,
  withdrawals_30d_usd: null,
  last_withdrawal_at: null,
  pending_withdrawal_usd: null,
  bonuses_30d_usd: null,
  bonuses_30d_count: null,
  last_login_at: null,
  birthday: null,
  favorite_game: null,
  deposits_change_pct: null,
  deposit_drop: null,
};

function player(profile: Partial<PlayerProfile>): Player {
  return {
    player_id: "T1",
    display_name: null,
    manager_id: "Ольга",
    segment: "VIP",
    country: "CIS",
    registered_at: "2025-01-01",
    profile: { ...EMPTY, ...profile },
  };
}

function renderCard(p: Player) {
  serveApi(vi, { "/api/queue": [] });
  return render(
    <MemoryRouter>
      <Dossier player={p} currentId="D1" />
    </MemoryRouter>,
  );
}

function row(group: HTMLElement, term: string): string {
  const dt = within(group).getByText(term, { selector: "dt" });
  return dt.nextElementSibling?.textContent ?? "";
}

describe("player card", () => {
  it("shows every profile column in groups", () => {
    renderCard(
      player({
        account_status: "active",
        brand: "ACME",
        language: "ru",
        geo: "CIS",
        deposits_30d_usd: 1000,
        deposits_30d_count: 5,
        deposits_prev_30d_usd: 900,
        deposits_prev_30d_count: 4,
        last_deposit_at: "2026-01-10",
        failed_deposits_7d: 2,
        withdrawals_30d_usd: 300,
        pending_withdrawal_usd: 2800,
        bonuses_30d_usd: 50,
        bonuses_30d_count: 1,
        last_login_at: "2026-01-11",
        birthday: "1990-01-01",
        favorite_game: "Demo Slot",
      }),
    );
    const account = screen.getByRole("region", { name: "Аккаунт" });
    expect(row(account, "Статус")).toBe("Активен");
    expect(row(account, "Бренд")).toBe("ACME");
    expect(row(account, "Язык")).toBe("русский");

    const money = screen.getByRole("region", { name: "Деньги" });
    expect(row(money, "Депозиты 30 дн.")).toBe("$1 000 · 5 шт.");
    expect(row(money, "Пред. 30 дн.")).toBe("$900 · 4 шт.");
    expect(row(money, "Неудачные депозиты 7 дн.")).toBe("2");
    expect(row(money, "Последний вывод")).toBe("—");
    expect(row(money, "Бонусы 30 дн.")).toBe("$50 · 1 шт.");
    const pending = within(money).getByText("$2 800");
    expect(pending).toHaveAttribute("data-alert", "true");

    const personal = screen.getByRole("region", { name: "Личное" });
    expect(row(personal, "Любимая игра")).toBe("Demo Slot");
    expect(within(screen.getByRole("region", { name: "Активность" })).getByText("Последний вход")).toBeInTheDocument();
  });

  it("warns about a self-excluded or limited account", () => {
    renderCard(player({ account_status: "self_excluded" }));
    expect(screen.getByRole("note")).toHaveTextContent(/Самоисключение/);

    renderCard(player({ account_status: "limit_set" }));
    expect(screen.getAllByRole("note").at(-1)).toHaveTextContent(/Установлен лимит/);
  });

  it("shows missing values as a dash, never invented", () => {
    renderCard(player({}));
    const money = screen.getByRole("region", { name: "Деньги" });
    expect(row(money, "Вывод в ожидании")).toBe("—");
    expect(row(screen.getByRole("region", { name: "Аккаунт" }), "Статус")).toBe("—");
  });
});

describe("player card: language and deposit change", () => {
  it("names the language and shows the 30-day change, highlighting a drop past the threshold", () => {
    renderCard(
      player({
        language: "ru",
        deposits_30d_usd: 100,
        deposits_30d_count: 1,
        deposits_change_pct: -90,
        deposit_drop: true,
      }),
    );
    const account = screen.getByRole("region", { name: "Аккаунт" });
    expect(row(account, "Язык")).toBe("русский");
    const money = screen.getByRole("region", { name: "Деньги" });
    expect(row(money, "Депозиты 30 дн.")).toBe("$100 · 1 шт. · −90%");
    expect(within(money).getByText("−90%")).toHaveAttribute("data-alert", "true");
  });

  it("shows an unknown language code as it is", () => {
    renderCard(player({ language: "xx" }));
    expect(row(screen.getByRole("region", { name: "Аккаунт" }), "Язык")).toBe("xx");
  });
});

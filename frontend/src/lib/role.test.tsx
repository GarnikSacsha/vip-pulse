import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { parseRole, sectionsOf } from "./role";
import { conversation, meta, overview, queueItem, serveApi } from "../test/fixtures";

const KEY = "vip-pulse-role";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function routes() {
  return { "/api/meta": meta, "/api/queue": [queueItem()], "/api/winback": [], "/api/overview": overview };
}

function navLinks(): string[] {
  return within(screen.getByRole("navigation", { name: "Разделы" }))
    .getAllByRole("link")
    .map((a) => a.textContent ?? "");
}

afterEach(() => localStorage.clear());

describe("demo role switcher", () => {
  it("lists the managers from the data and says it is a demo, not authorisation", async () => {
    serveApi(vi, routes());
    renderAt("/queue");
    const select = await screen.findByRole("combobox", { name: /Роль/ });
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Все разделы", "Я: mgr-01", "Я: mgr-02", "Тимлид", "Руководитель"]);
    expect(screen.getByText("демо-режим")).toHaveAttribute("title", expect.stringMatching(/не вход/));
  });

  it("shows a manager only their own queue and win-back list", async () => {
    const calls = serveApi(vi, routes());
    renderAt("/queue");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: /Роль/ }), "Я: mgr-01");
    expect(navLinks()).toEqual(["Очередь", "Кого вернуть"]);
    expect(calls.some((u) => u.startsWith("/api/queue") && u.includes("manager=mgr-01"))).toBe(true);
    // No "remove filter" chip: the role is the filter.
    expect(screen.queryByRole("button", { name: /снять фильтр/ })).not.toBeInTheDocument();
    expect(localStorage.getItem(KEY)).toBe("manager:mgr-01");
  });

  it("keeps a manager out of the team and overview pages", async () => {
    localStorage.setItem(KEY, "manager:mgr-02");
    serveApi(vi, routes());
    renderAt("/lead");
    expect(await screen.findByRole("list", { name: "Очередь" })).toBeInTheDocument();
  });

  it("filters the win-back list by the manager role", async () => {
    localStorage.setItem(KEY, "manager:mgr-02");
    const calls = serveApi(vi, routes());
    renderAt("/winback");
    await screen.findByRole("heading", { name: "Кого вернуть" });
    expect(calls).toContain("/api/winback?manager=mgr-02");
  });

  it("gives the lead the whole queue and the team page", async () => {
    localStorage.setItem(KEY, "lead");
    serveApi(vi, routes());
    renderAt("/queue");
    await screen.findByRole("list", { name: "Очередь" });
    expect(navLinks()).toEqual(["Очередь", "Команда"]);
  });

  it("starts the head of VIP on the overview, with the team page and a read-only queue", async () => {
    localStorage.setItem(KEY, "head");
    serveApi(vi, routes());
    renderAt("/");
    expect(await screen.findByRole("heading", { name: /Обзор|Сводка/ })).toBeInTheDocument();
    expect(navLinks()).toEqual(["Обзор", "Команда", "Очередь"]);
  });
});

describe("demo roles: links and read-only queue", () => {
  it("opens «Открыть критичные» for the head of VIP as a read-only queue", async () => {
    localStorage.setItem(KEY, "head");
    serveApi(vi, { ...routes(), "/api/conversations/d-001": conversation() });
    renderAt("/queue/d-001?priority=P0");
    expect(await screen.findByRole("list", { name: "Очередь" })).toBeInTheDocument();
    expect(navLinks()).toEqual(["Обзор", "Команда", "Очередь"]);
    expect(await screen.findByText(/Режим просмотра/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Действия" })).not.toBeInTheDocument();
  });

  it.each([
    ["all", ["/queue", "/winback", "/lead", "/overview"]],
    ["manager:mgr-01", ["/queue", "/winback"]],
    ["lead", ["/queue", "/lead"]],
    ["head", ["/overview", "/lead", "/queue"]],
  ])("every link visible to %s opens a page that role can see", async (value, pages) => {
    localStorage.setItem(KEY, value);
    const winback = [
      {
        player: { player_id: "p-041", display_name: null, manager_id: "mgr-01", segment: "VIP" },
        tier: "urgent",
        reasons: [],
        next_action: "x",
        last_login_days: 20,
        last_contact_days: 3,
        deposits_30d_usd: 0,
        deposits_prev_30d_usd: 100,
        favorite_game: null,
        latest_conversation_id: "d-001",
      },
    ];
    serveApi(vi, { ...routes(), "/api/winback": winback, "/api/birthdays": [] });
    for (const page of pages.filter((p) => sectionsOf(parseRole(value)).includes(p))) {
      const { unmount } = renderAt(page);
      await screen.findByRole("navigation", { name: "Разделы" });
      await screen.findAllByRole("heading", { level: 1 }).catch(() => null);
      const hrefs = screen
        .getAllByRole("link")
        .map((a) => a.getAttribute("href") ?? "")
        .filter((h) => h.startsWith("/"));
      for (const href of hrefs) {
        const section = "/" + (href.split(/[/?#]/)[1] ?? "");
        expect(sectionsOf(parseRole(value)), `${value} on ${page}: ${href}`).toContain(section);
      }
      unmount();
    }
  });
});

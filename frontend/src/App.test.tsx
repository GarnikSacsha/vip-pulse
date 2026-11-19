import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "./App";
import type { Meta } from "./api/types";

function meta(simulated: boolean): Meta {
  return {
    as_of: "2026-11-12T13:00:00Z",
    provider: {
      name: simulated ? "fake" : "gemini",
      model: simulated ? "heuristic-v1" : "gemini-2.5-flash",
      simulated,
      label: simulated ? "эвристика fake, без модели" : "AI",
      budget_usd: simulated ? null : 1,
      spent_usd: simulated ? null : 0,
    },
    counts: {
      total: 9,
      by_status: { open: 5, in_progress: 0, resolved: 0, no_action: 4 },
      by_priority: { P0: 3, P1: 1, P2: 1, P3: 4 },
    },
  };
}

function serve(routes: Record<string, unknown>) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input).split("?")[0] ?? "";
    if (!(path in routes)) return new Response("{}", { status: 404 });
    return new Response(JSON.stringify(routes[path]), { status: 200 });
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("app shell", () => {
  it("shows the product name and the dataset date", async () => {
    serve({ "/api/meta": meta(false), "/api/queue": [] });
    renderAt("/queue");
    expect(screen.getByText("VIP Pulse")).toBeInTheDocument();
    expect(await screen.findByText(/Данные на 12 ноября 2026, 13:00 UTC/)).toBeInTheDocument();
  });

  it("warns that the analysis is simulated in demo mode", async () => {
    serve({ "/api/meta": meta(true), "/api/queue": [] });
    renderAt("/queue");
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("Демо-режим");
    expect(banner).toHaveTextContent("эвристика fake, без модели");
  });

  it("shows no demo banner when a real model is configured", async () => {
    serve({ "/api/meta": meta(false), "/api/queue": [] });
    renderAt("/queue");
    await screen.findByText(/Данные на/);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("explains when the API is unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("down", { status: 502 }));
    renderAt("/queue");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0]).toHaveTextContent("Сервер недоступен (502)");
  });
});

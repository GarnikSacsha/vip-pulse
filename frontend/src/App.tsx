import { NavLink, Navigate, Outlet, Route, Routes } from "react-router";
import { api } from "./api/client";
import { formatDateTime } from "./lib/format";
import { ConversationPage } from "./pages/ConversationPage";
import { QueuePage, type ShellContext } from "./pages/QueuePage";
import { useApi } from "./lib/useApi";

function Shell() {
  const meta = useApi(() => api.meta(), "meta");

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-semibold tracking-tight">VIP Pulse</span>
            <span className="hidden text-sm text-muted sm:inline">разбор переписок VIP-отдела</span>
          </div>
          <nav className="flex gap-1 text-sm">
            <NavLink
              to="/queue"
              className={({ isActive }) =>
                `rounded-md px-2.5 py-1 ${isActive ? "bg-chip text-ink" : "text-muted hover:text-ink"}`
              }
            >
              Очередь
            </NavLink>
          </nav>
          <div className="ml-auto text-xs text-muted">
            {meta.data?.as_of && <>Данные на {formatDateTime(meta.data.as_of)}</>}
          </div>
        </div>
      </header>

      {meta.error && (
        <div role="alert" className="border-b border-danger-line bg-danger-soft">
          <p className="mx-auto max-w-6xl px-4 py-2 text-sm text-danger sm:px-6">
            {meta.error}. Запустите API: <code className="font-mono">uvicorn app.main:create_app --factory</code>
          </p>
        </div>
      )}

      {meta.data?.provider.simulated && (
        <div role="status" className="border-b border-warn-line bg-warn-soft">
          <p className="mx-auto max-w-6xl px-4 py-2 text-sm text-warn sm:px-6">
            <strong className="font-medium">Демо-режим.</strong> Разбор переписок выполняет{" "}
            {meta.data.provider.label}: категории и советы ниже — заглушка для проверки интерфейса,
            а не вывод языковой модели.
          </p>
        </div>
      )}

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet context={{ meta: meta.data } satisfies ShellContext} />
      </main>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/queue" replace />} />
        <Route path="queue" element={<QueuePage />} />
        <Route path="conversations/:id" element={<ConversationPage />} />
      </Route>
    </Routes>
  );
}

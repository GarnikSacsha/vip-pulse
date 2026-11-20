import { NavLink, Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router";
import { api } from "./api/client";
import { formatDateTime } from "./lib/format";
import { ConversationPane, NoConversation } from "./pages/ConversationPage";
import { LeadPage } from "./pages/LeadPage";
import { OverviewPage } from "./pages/OverviewPage";
import { WinbackPage } from "./pages/WinbackPage";
import { QueuePage, type ShellContext } from "./pages/QueuePage";
import { useApi } from "./lib/useApi";

const NAV = [
  { to: "/queue", label: "Очередь", hint: "менеджер" },
  { to: "/winback", label: "Кого вернуть", hint: "менеджер" },
  { to: "/lead", label: "Команда", hint: "тимлид" },
  { to: "/overview", label: "Обзор", hint: "руководитель VIP" },
];

function Shell() {
  const meta = useApi(() => api.meta(), "meta");

  return (
    // On wide screens the shell fills the viewport and each pane scrolls on its own.
    <div className="flex min-h-screen flex-col bg-canvas text-ink lg:h-screen">
      <header className="shrink-0 border-b border-line bg-surface">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-semibold tracking-tight">
              VIP Pulse
            </span>
            <span className="hidden text-sm text-muted sm:inline">разбор переписок VIP-отдела</span>
          </div>
          <nav aria-label="Разделы" className="flex gap-1 text-sm">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                title={`Для роли: ${n.hint}`}
                className={({ isActive }) =>
                  `rounded-md px-2.5 py-1 ${isActive ? "bg-chip text-ink" : "text-muted hover:text-ink"}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto text-xs text-muted">
            {meta.data?.as_of && <>Данные на {formatDateTime(meta.data.as_of)}</>}
          </div>
        </div>
      </header>

      {meta.error && (
        <div role="alert" className="shrink-0 border-b border-danger-line bg-danger-soft">
          <p className="px-4 py-2 text-sm text-danger sm:px-6">
            {meta.error}. Запустите API: <code className="font-mono">uvicorn app.main:create_app --factory</code>
          </p>
        </div>
      )}

      {meta.data?.provider.simulated && (
        <div role="status" className="hatch shrink-0 border-b border-warn-line bg-warn-soft">
          <p className="px-4 py-2 text-sm text-warn sm:px-6">
            <strong className="font-medium">Демо-режим.</strong> Разбор переписок выполняет{" "}
            {meta.data.provider.label}: категории и советы ниже — заглушка для проверки интерфейса,
            а не вывод языковой модели.
          </p>
        </div>
      )}

      <main className="flex-1 lg:min-h-0 lg:overflow-y-auto">
        <Outlet context={{ meta: meta.data, reloadMeta: meta.reload } satisfies ShellContext} />
      </main>
    </div>
  );
}

/** Oversight pages: centred, document-style. */
function Contained() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <Outlet />
    </div>
  );
}

/** Old /conversations/:id links (bookmarks, earlier builds) open in the inbox. */
function ToInbox() {
  const { id = "" } = useParams();
  const { search } = useLocation();
  return <Navigate to={`/queue/${encodeURIComponent(id)}${search}`} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/queue" replace />} />
        <Route path="queue" element={<QueuePage />}>
          <Route index element={<NoConversation />} />
          <Route path=":id" element={<ConversationPane />} />
        </Route>
        <Route path="conversations/:id" element={<ToInbox />} />
        <Route element={<Contained />}>
          <Route path="winback" element={<WinbackPage />} />
          <Route path="lead" element={<LeadPage />} />
          <Route path="overview" element={<OverviewPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

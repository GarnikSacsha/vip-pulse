import { Link } from "react-router";
import { api } from "../api/client";
import type { CategoryCount, ChannelCount, Overview } from "../api/types";
import { ErrorBox, InlineBar, KpiList, LoadingBlocks, Panel, plural } from "../components/Oversight";
import { formatDateTime } from "../lib/format";
import { CATEGORY_LABEL, CHANNEL_LABEL, ROUTE_LABEL } from "../lib/labels";
import { useApi } from "../lib/useApi";

export function OverviewPage() {
  const overview = useApi(() => api.overview(), "overview");

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Обзор VIP-отдела</h1>
          <p className="mt-0.5 text-sm text-muted">Срез по загруженным диалогам: где риск и куда смотреть первым.</p>
        </div>
        <Link
          to="/queue?priority=P0"
          className="rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-white hover:bg-ink/90"
        >
          Открыть критичные
        </Link>
      </div>

      {overview.error ? (
        <ErrorBox message={`Не удалось загрузить обзор: ${overview.error}`} onRetry={overview.reload} />
      ) : !overview.data ? (
        <LoadingBlocks />
      ) : (
        <OverviewBody data={overview.data} />
      )}
    </section>
  );
}

function OverviewBody({ data }: { data: Overview }) {
  const t = data.totals;
  const withinSla = t.awaiting_reply - t.overdue;
  return (
    <>
      <KpiList
        items={[
          { label: "Ждут действий", value: `${t.active} из ${t.total}`, hint: "открытые и в работе" },
          { label: "Критичные", value: t.critical, tone: t.critical ? "alert" : "plain", hint: "приоритет P0" },
          {
            label: "Ответ в рамках SLA",
            value: t.awaiting_reply ? `${withinSla} из ${t.awaiting_reply}` : "—",
            hint: "среди ждущих ответа",
            tone: t.overdue ? "alert" : "plain",
          },
          { label: "Сигналы безопасности", value: t.escalated, hint: "ответственная игра и взломы" },
          { label: "Ошибки менеджеров", value: t.quality_issues, tone: t.quality_issues ? "alert" : "plain" },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <Categories categories={data.categories} />
        <div className="space-y-4">
          <Channels channels={data.channels} />
          <Routes routes={data.routes} />
        </div>
      </div>

      <Source data={data} />
    </>
  );
}

function Categories({ categories }: { categories: CategoryCount[] }) {
  const max = Math.max(0, ...categories.map((c) => c.active));
  return (
    <Panel id="categories" title="Запросы по категориям" description="Категорию определяет разбор переписки.">
      {categories.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted">Нет данных.</p>
      ) : (
        <div className="overflow-x-auto">
          <table aria-label="Запросы по категориям" className="w-full min-w-[22rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Категория</th>
                <th className="px-3 py-2 font-medium">Активные</th>
                <th className="px-4 py-2 text-right font-medium">Всего</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line border-t border-line tabular-nums">
              {categories.map((c) => {
                const label = c.category ? CATEGORY_LABEL[c.category] : "Разбор не выполнен";
                return (
                  <tr key={c.category ?? "failed"}>
                    <th scope="row" className="px-4 py-2 text-left font-normal">
                      {label}
                    </th>
                    <td className="px-3 py-2">
                      <InlineBar value={c.active} max={max} label={`${label}: активных ${c.active}`} />
                    </td>
                    <td className="px-4 py-2 text-right text-muted">{c.total}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Channels({ channels }: { channels: ChannelCount[] }) {
  return (
    <Panel id="channels" title="Каналы">
      <div className="overflow-x-auto">
        <table aria-label="Каналы" className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Канал</th>
              <th className="px-3 py-2 text-right font-medium">Активные</th>
              <th className="px-3 py-2 text-right font-medium">Просрочено</th>
              <th className="px-4 py-2 text-right font-medium">Всего</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line border-t border-line tabular-nums">
            {channels.map((c) => (
              <tr key={c.channel}>
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  {CHANNEL_LABEL[c.channel]}
                </th>
                <td className="px-3 py-2 text-right">{c.active}</td>
                <td className={`px-3 py-2 text-right ${c.overdue ? "font-medium text-danger" : ""}`}>{c.overdue}</td>
                <td className="px-4 py-2 text-right text-muted">{c.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Routes({ routes }: { routes: Overview["routes"] }) {
  return (
    <Panel id="routes" title="Кто ведёт активные диалоги">
      <dl className="divide-y divide-line text-sm">
        {(Object.keys(routes) as (keyof typeof routes)[]).map((r) => (
          <div key={r} className="flex justify-between px-4 py-2">
            <dt>{ROUTE_LABEL[r]}</dt>
            <dd className="tabular-nums">{routes[r]}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function Source({ data }: { data: Overview }) {
  const c = data.coverage;
  return (
    <Panel id="source" title="Откуда цифры">
      <div className="space-y-2 px-4 py-3 text-sm text-muted">
        <p>
          {c.conversations} {plural(c.conversations, ["диалог", "диалога", "диалогов"])}
          {data.as_of && <> на {formatDateTime(data.as_of)}</>}. Разобрано {c.analysed}, не удалось {c.failed}.{" "}
          {c.simulated ? (
            <strong className="font-medium text-warn">
              Категории посчитала эвристика без модели: это демо-режим, а не вывод языковой модели.
            </strong>
          ) : (
            <>Категории определила языковая модель; приоритеты и SLA считает код.</>
          )}
        </p>
        <p>
          «Просрочено» — игрок ждёт ответа дольше порога своего канала. Пороги — допущения из{" "}
          <code className="font-mono text-xs">thresholds.yaml</code>, их нужно согласовать с отделом.
        </p>
        <p>Динамики пока нет: загружен срез на одну дату. Тренды появятся, когда будут данные за несколько дней.</p>
      </div>
    </Panel>
  );
}

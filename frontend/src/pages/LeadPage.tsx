import { Link } from "react-router";
import { api } from "../api/client";
import type { ManagerLoad, Overview, QueueItem } from "../api/types";
import { CompactItem, ErrorBox, KpiList, LoadingBlocks, Panel } from "../components/Oversight";
import { formatWait } from "../lib/format";
import { useApi } from "../lib/useApi";

interface Group {
  id: string;
  title: string;
  description: string;
  pick: (item: QueueItem) => boolean;
}

// Each active item can appear in several groups: they answer different questions.
const GROUPS: Group[] = [
  {
    id: "overdue",
    title: "Просрочен ответ",
    description: "Игрок ждёт дольше порога SLA своего канала.",
    pick: (i) => i.overdue,
  },
  {
    id: "escalated",
    title: "Эскалации",
    description: "Ведёт не менеджер: специалист по ответственной игре или безопасность.",
    pick: (i) => i.route !== "manager",
  },
  {
    id: "quality",
    title: "Ошибки менеджеров",
    description: "Например, бонус игроку с сигналом ответственной игры.",
    pick: (i) => i.quality_flags.length > 0,
  },
  {
    id: "review",
    title: "Нужна ручная проверка",
    description: "Автоматический разбор не выполнен или неуверен.",
    pick: (i) => i.requires_review,
  },
];

export function LeadPage() {
  const overview = useApi(() => api.overview(), "overview");
  const active = useApi(() => api.queue({ status: ["open", "in_progress"] }), "lead-active");

  const error = overview.error ?? active.error;
  if (error) {
    return (
      <ErrorBox
        message={`Не удалось загрузить данные: ${error}`}
        onRetry={() => {
          overview.reload();
          active.reload();
        }}
      />
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Контроль команды</h1>
        <p className="mt-0.5 text-sm text-muted">
          Что просрочено, что ушло в эскалацию и где менеджер ошибся. Только активные диалоги.
        </p>
      </div>

      {!overview.data || !active.data ? (
        <LoadingBlocks />
      ) : (
        <LeadBody overview={overview.data} active={active.data} />
      )}
    </section>
  );
}

function LeadBody({ overview, active }: { overview: Overview; active: QueueItem[] }) {
  return (
    <>
      <LeadKpis overview={overview} />
      <Workload managers={overview.managers} />
      <div className="grid gap-4 lg:grid-cols-2">
        {GROUPS.map((g) => (
          <ExceptionGroup key={g.id} group={g} items={active.filter(g.pick)} />
        ))}
      </div>
    </>
  );
}

function LeadKpis({ overview }: { overview: Overview }) {
  const t = overview.totals;
  return (
    <KpiList
      items={[
        { label: "Активные", value: t.active, hint: `в работе ${t.in_progress}` },
        { label: "Просрочен ответ", value: t.overdue, tone: t.overdue ? "alert" : "plain" },
        { label: "Эскалации", value: t.escalated, hint: "RG и безопасность" },
        { label: "Ошибки менеджеров", value: t.quality_issues, tone: t.quality_issues ? "alert" : "plain" },
        { label: "Нужна проверка", value: t.needs_review },
      ]}
    />
  );
}

function Workload({ managers }: { managers: ManagerLoad[] }) {
  return (
    <Panel
      id="workload"
      title="Нагрузка по менеджерам"
      description="Закрепление игрока за менеджером взято из players.csv. Имя менеджера открывает его очередь."
    >
      {managers.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted">Нет данных: импортируйте игроков и диалоги.</p>
      ) : (
        <div className="overflow-x-auto">
          <table aria-label="Нагрузка по менеджерам" className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Менеджер</th>
                <th className="px-3 py-2 text-right font-medium">Активные</th>
                <th className="px-3 py-2 text-right font-medium">В работе</th>
                <th className="px-3 py-2 text-right font-medium">Критичные</th>
                <th className="px-3 py-2 text-right font-medium">Просрочено</th>
                <th className="px-3 py-2 text-right font-medium">Дольше всех ждёт</th>
                <th className="px-4 py-2 text-right font-medium">Всего</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line border-t border-line tabular-nums">
              {managers.map((m) => (
                <tr key={m.manager_id ?? "none"}>
                  <th scope="row" className="px-4 py-2.5 text-left font-medium">
                    {m.manager_id ? (
                      <Link
                        to={`/queue?manager=${encodeURIComponent(m.manager_id)}`}
                        className="underline decoration-line underline-offset-4 hover:decoration-ink"
                      >
                        {m.manager_id}
                      </Link>
                    ) : (
                      <span className="text-danger">Без менеджера</span>
                    )}
                  </th>
                  <td className="px-3 py-2.5 text-right">{m.active}</td>
                  <td className="px-3 py-2.5 text-right">{m.in_progress}</td>
                  <td className="px-3 py-2.5 text-right">{m.critical}</td>
                  <td className={`px-3 py-2.5 text-right ${m.overdue ? "font-medium text-danger" : ""}`}>{m.overdue}</td>
                  <td className="px-3 py-2.5 text-right">{formatWait(m.oldest_wait_hours)}</td>
                  <td className="px-4 py-2.5 text-right text-muted">{m.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function ExceptionGroup({ group, items }: { group: Group; items: QueueItem[] }) {
  return (
    <Panel
      id={`group-${group.id}`}
      title={
        <>
          {group.title} <span className="font-normal tabular-nums text-muted">· {items.length}</span>
        </>
      }
      description={group.description}
    >
      {items.length === 0 ? (
        <p className="px-4 py-4 text-sm text-muted">Нет</p>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <li key={item.task_id}>
              <CompactItem item={item} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

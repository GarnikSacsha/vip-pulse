import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { WinbackItem, WinbackTier } from "../api/types";
import { Tag } from "../components/Badges";
import { ErrorBox, LoadingBlocks } from "../components/Oversight";
import { useApi } from "../lib/useApi";

const TIERS: { tier: WinbackTier; title: string; hint: string; tone: string }[] = [
  {
    tier: "urgent",
    title: "Вернуть срочно",
    hint: "Давно не заходит или перестал вносить депозиты.",
    tone: "text-danger",
  },
  { tier: "attention", title: "Внимание", hint: "Депозиты резко упали.", tone: "text-p1" },
  {
    tier: "introduce",
    title: "Познакомиться",
    hint: "Активен, но менеджер ещё ни разу не писал.",
    tone: "text-ink",
  },
];

const usd = (n: number | null) => (n === null ? "—" : `$${Math.round(n).toLocaleString("ru-RU")}`);

/**
 * Who to win back. Built in code from the profile and contact dates, for every player, including
 * those without a conversation. Restricted accounts never appear here.
 */
export function WinbackPage() {
  const [params, setParams] = useSearchParams();
  const manager = params.get("manager");
  const list = useApi(() => api.winback(manager), `winback:${manager ?? ""}`);

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Кого вернуть</h1>
        <p className="mt-0.5 text-sm text-muted">
          Игроки, которые замолчали или теряют интерес, — список собирается сам из данных игроков и
          дат переписок. Игроки с самоисключением или лимитом сюда не попадают.
        </p>
        {manager && (
          <button
            type="button"
            onClick={() => setParams({})}
            aria-label={`Менеджер ${manager}: снять фильтр`}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-chip px-2 py-0.5 text-xs font-medium hover:bg-line"
          >
            Менеджер {manager}
            <span aria-hidden="true">×</span>
          </button>
        )}
      </div>

      {list.error ? (
        <ErrorBox message={`Не удалось загрузить список: ${list.error}`} onRetry={list.reload} />
      ) : !list.data ? (
        <LoadingBlocks />
      ) : list.data.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line bg-surface px-4 py-10 text-center text-sm text-muted">
          Сейчас некого возвращать.
        </p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {TIERS.map(({ tier, title, hint, tone }) => {
            const items = (list.data ?? []).filter((i) => i.tier === tier);
            return (
              <section
                key={tier}
                aria-labelledby={`tier-${tier}`}
                className="flex min-w-0 flex-col rounded-lg bg-chip/60 p-2 ring-1 ring-line"
              >
                <header className="px-1.5 pb-2 pt-1">
                  <h2 id={`tier-${tier}`} className={`text-sm font-semibold ${tone}`}>
                    {title} <span className="font-normal tabular-nums text-muted">· {items.length}</span>
                  </h2>
                  <p className="text-xs text-muted">{hint}</p>
                </header>
                {items.length === 0 ? (
                  <p className="px-1.5 pb-2 text-sm text-muted">Пусто</p>
                ) : (
                  <ul className="space-y-2">
                    {items.map((i) => (
                      <li key={i.player.player_id}>
                        <WinbackCard item={i} />
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}

function WinbackCard({ item }: { item: WinbackItem }) {
  const name = item.player.display_name ?? item.player.player_id;
  return (
    <article className="rounded-md bg-surface p-3 text-sm ring-1 ring-line">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{name}</p>
          <p className="truncate text-xs text-muted">
            {[item.player.segment, item.player.manager_id ?? "без менеджера", item.favorite_game]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        {item.player.segment && <Tag>{item.player.segment}</Tag>}
      </div>

      <ul className="mt-2 space-y-1">
        {item.reasons.map((r) => (
          <li key={r.code} className="flex gap-2">
            <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted" />
            <span>{r.text}</span>
          </li>
        ))}
      </ul>

      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted">
        <dt>Депозиты 30 дн.</dt>
        <dd className="tabular-nums">
          {usd(item.deposits_prev_30d_usd)} → {usd(item.deposits_30d_usd)}
        </dd>
        <dt>Последний вход</dt>
        <dd className="tabular-nums">{item.last_login_days === null ? "—" : `${item.last_login_days} дн. назад`}</dd>
        <dt>Последняя переписка</dt>
        <dd className="tabular-nums">
          {item.last_contact_days === null ? "Переписок ещё не было" : `${item.last_contact_days} дн. назад`}
        </dd>
      </dl>

      <p className="mt-2 rounded bg-canvas px-2 py-1.5 text-xs leading-relaxed">{item.next_action}</p>
      {item.latest_conversation_id && (
        <Link
          to={`/queue/${encodeURIComponent(item.latest_conversation_id)}`}
          className="mt-2 inline-block text-xs font-medium text-accent hover:underline"
        >
          Открыть переписку →
        </Link>
      )}
    </article>
  );
}

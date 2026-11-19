const MONTHS = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

const pad = (n: number) => String(n).padStart(2, "0");

/** "12 ноября 2026, 13:00 UTC". Always UTC: the dataset has no single local timezone. */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${pad(
    d.getUTCHours(),
  )}:${pad(d.getUTCMinutes())} UTC`;
}

/** "12 ноя, 13:00" for message timestamps inside one conversation. */
export function formatShort(iso: string): string {
  const d = new Date(iso);
  const month = MONTHS[d.getUTCMonth()]?.slice(0, 3) ?? "";
  return `${d.getUTCDate()} ${month}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** Waiting time for a human: "40 мин", "6 ч", "1 д 3 ч". */
export function formatWait(hours: number | null): string {
  if (hours === null) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} мин`;
  const total = Math.round(hours);
  if (total < 24) return `${total} ч`;
  const days = Math.floor(total / 24);
  const rest = total % 24;
  return rest ? `${days} д ${rest} ч` : `${days} д`;
}

/** "11 апреля 2023" for a calendar date ("2023-04-11"); unparsable input is returned as is. */
export function formatDay(value: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!m) return value;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1] ?? ""} ${m[1]}`;
}

import type { Category, Channel, Priority, Route, SenderRole, TaskStatus } from "../api/types";

export const PRIORITY_LABEL: Record<Priority, string> = {
  P0: "Критично",
  P1: "Высокий",
  P2: "Средний",
  P3: "Низкий",
};

export const CATEGORY_LABEL: Record<Category, string> = {
  withdrawal: "Вывод средств",
  deposit: "Депозит",
  verification: "Верификация",
  account: "Аккаунт и безопасность",
  technical: "Техническая проблема",
  general: "Общее",
  responsible_gaming: "Ответственная игра",
  other: "Без категории",
};

export const CHANNEL_LABEL: Record<Channel, string> = {
  telegram: "Telegram",
  whatsapp: "WhatsApp",
  email: "Email",
  other: "Другой канал",
};

export const ROUTE_LABEL: Record<Route, string> = {
  manager: "Менеджер",
  rg_specialist: "Специалист по ответственной игре",
  security: "Служба безопасности",
};

export const STATUS_LABEL: Record<TaskStatus, string> = {
  open: "Открыта",
  in_progress: "В работе",
  resolved: "Решено",
  no_action: "Без действий",
};

export const SENDER_LABEL: Record<SenderRole, string> = {
  player: "Игрок",
  manager: "Менеджер",
  system: "Система",
};

const QUALITY_FLAG_LABEL: Record<string, string> = {
  offer_to_vulnerable_player: "Бонус уязвимому игроку",
};

export function qualityFlagLabel(flag: string): string {
  return QUALITY_FLAG_LABEL[flag] ?? flag;
}

import type { Category, Channel, ManagerErrorCode, Priority, Route, SenderRole, Sentiment, SlaLane, TaskStatus } from "../api/types";

export const PRIORITY_LABEL: Record<Priority, string> = {
  P0: "Критично",
  P1: "Высокий",
  P2: "Средний",
  P3: "Низкий",
};

/** For «Приоритет: …» in a sentence. */
export const PRIORITY_NAME: Record<Priority, string> = {
  P0: "критичный",
  P1: "высокий",
  P2: "средний",
  P3: "низкий",
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

export const SLA_LANE_LABEL: Record<SlaLane, string> = {
  breached: "Горит",
  at_risk: "Скоро нарушится",
  waiting: "Ждёт",
  specialist: "У специалиста",
  ok: "Всё ок",
};

export const SENTIMENT_LABEL: Record<Sentiment, string> = {
  positive: "позитивный",
  neutral: "нейтральный",
  negative: "негативный",
  mixed: "смешанный",
};

export const SENDER_LABEL: Record<SenderRole, string> = {
  player: "Игрок",
  manager: "Менеджер",
  system: "Система",
};

const QUALITY_FLAG_LABEL: Record<string, string> = {
  offer_to_vulnerable_player: "Бонус уязвимому игроку",
  offer_to_restricted_player: "Бонус игроку с ограничением",
};

/** Alerts that need the manager personally: short tag, headline and what to do. */
export const ALERT_TEXT: Record<string, { tag: string; title: string; action: string }> = {
  multi_account: {
    tag: "Связаться лично",
    title: "Возможен второй аккаунт или общая карта",
    action:
      "Свяжитесь с игроком лично: уточните, чей это аккаунт и чья карта. Бонус на другой аккаунт не начисляйте до проверки.",
  },
};

export function alertText(alert: string): { tag: string; title: string; action: string } {
  return ALERT_TEXT[alert] ?? { tag: "Связаться лично", title: alert, action: "Свяжитесь с игроком лично." };
}

export const MANAGER_ERROR_LABEL: Record<ManagerErrorCode, string> = {
  canned_reply: "Шаблонная отписка",
  rude_tone: "Грубый тон",
  wrong_info: "Неверная информация",
  incomplete_answer: "Вопрос без ответа по существу",
  wrong_name: "Ошибка в имени или данных игрока",
  broken_promise: "Обещал вернуться и не вернулся",
  retention_pressure: "Давление: играть дальше или не выводить",
};

/** What a manager sees for a case escalated to a specialist (the lead sees the analysis). */
export const HANDED_OVER_STEP = "Передано специалисту: не писать игроку о бонусах и акциях; подтвердить получение.";

/** Manager mistakes counted by code from message times (decision 0019). */
export const RULE_ERROR_LABEL: Record<string, string> = {
  late_reply: "Ответ позже SLA канала",
  waiting_past_sla: "Игрок ждёт дольше SLA",
  offer_before_security_check: "Бонус до проверки безопасности",
};

export function qualityFlagLabel(flag: string): string {
  return QUALITY_FLAG_LABEL[flag] ?? flag;
}

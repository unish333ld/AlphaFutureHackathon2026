import type {
  ActionName,
  Application,
  Revision,
  Status,
} from "../shared/api/client";

export const statuses: Record<Status, string> = {
  draft: "Черновик",
  submitted: "Заявка отправлена",
  checking: "Проверки",
  review: "На рассмотрении",
  needs_info: "Проверьте данные",
  offered: "Есть предложение",
  accepted: "Условия приняты",
  signed: "Договор подписан",
  issued: "Выдача завершена",
  rejected: "Отказ",
  declined: "Предложение отклонено",
  expired: "Срок истёк",
};
export const nextSteps: Record<Status, string> = {
  draft:
    "Заполните параметры и показатели, проверьте заявку и отправьте её на рассмотрение.",
  submitted: "Заявка получена. Дождитесь завершения проверок.",
  checking:
    "Проверяем заявку. Если проверка прервётся, её можно будет повторить.",
  review: "Заявка у специалиста. Сообщим, когда появится результат.",
  needs_info:
    "Проверьте указанные специалистом сведения и отправьте исправленную заявку.",
  offered:
    "Ознакомьтесь с решением и условиями. Примите предложение либо отклоните его.",
  accepted: "Предложение принято. Ознакомьтесь с договором и подпишите его.",
  signed: "Договор подписан. Ожидается выдача специалистом.",
  issued: "Выдача завершена. Результат и договор доступны в карточке.",
  rejected:
    "По заявке принято отрицательное решение. Причина указана в карточке.",
  declined: "Вы отклонили предложение. Эта заявка завершена.",
  expired: "Срок предложения или подписания истёк. Заявка завершена.",
};
export const actionLabels: Record<ActionName, string> = {
  update_draft: "Продолжить черновик",
  submit: "Отправить заявку",
  retry_checks: "Повторить проверку",
  provide_information: "Проверьте данные заявки",
  revise: "Пересмотреть параметры",
  claim: "Взять в работу",
  release: "Освободить заявку",
  request_information: "Запросить проверку данных",
  decide: "Принять решение по правилам",
  accept_offer: "Принять предложение",
  decline_offer: "Отклонить предложение",
  sign_agreement: "Подписать договор",
  disburse: "Моделировать выдачу",
};
export function displayName(value: string | null | undefined) {
  return (value ?? "")
    .replace(/^Демо\s*·\s*/i, "")
    .replace(/\s*·\s*демо$/i, "");
}
export const reasons: Record<string, string> = {
  role_required: "Действие недоступно вашей роли.",
  capability_required: "У вас нет необходимых полномочий.",
  assignment_required: "Сначала возьмите заявку в работу.",
  assigned_to_other: "Заявка занята другим специалистом.",
  already_assigned: "Заявка уже назначена вам.",
  not_assigned: "У заявки нет исполнителя.",
  needs_information: "Ожидаются сведения от клиента.",
  technical_error: "Проверка завершилась технической ошибкой.",
  retry_limit: "Достигнут лимит пяти попыток проверки.",
  waiting_for_client: "Ожидается действие клиента.",
  offer_expired: "Предложение или срок подписи недоступны. Обновите карточку.",
  assessment_unavailable: "У текущей ревизии пока нет оценки.",
  assessment_outdated: "Оценка больше не соответствует проверкам.",
  checks_incomplete: "Проверки текущей ревизии не завершены.",
  already_completed: "Действие уже завершено.",
  no_current_revision: "Нет актуальной ревизии.",
  terms_mismatch: "Принятые условия не совпадают с текущей версией.",
  product_unavailable: "Продукт больше не принимает заявки.",
  invalid_terms: "Параметры вне границ продукта.",
  invalid_state: "В текущем состоянии действие недоступно.",
};
export const riskLabels = { low: "Низкий", medium: "Средний", high: "Высокий" };
export const checkLabels = {
  registry: "Регистрационный статус",
  credit_history: "Кредитная история",
  financial: "Финансовые сведения",
};
export const checkStatuses = {
  passed: "Пройдена",
  failed: "Негативный результат",
  missing: "Недостаточно данных",
  error: "Техническая ошибка",
};
export function currentRevision(app: Application): Revision | null {
  if (!app.current_revision_id) return null;
  return (
    app.revisions.find((revision) => revision.id === app.current_revision_id) ??
    null
  );
}
export function actionFor(app: Application, name: ActionName) {
  return app.available_actions.find((action) => action.action === name);
}
export function currentAssessment(revision: Revision | null) {
  if (!revision || revision.assessment?.revision !== revision.id) return null;
  const latestAttempt = Math.max(
    0,
    ...(revision.checks ?? []).map((check) => check.attempt),
  );
  if (latestAttempt && revision.assessment.checks_attempt !== latestAttempt)
    return null;
  return revision.assessment;
}
export function currentOffer(app: Application) {
  const assessment = currentAssessment(currentRevision(app));
  return assessment?.decision?.assessment === assessment?.id
    ? (assessment?.decision?.offer ?? null)
    : null;
}
export function normalizeMoney(raw: string): string | null {
  const value = raw.replace(/[\s\u00a0\u202f]/g, "").replace(",", ".");
  if (!/^\d{1,16}(?:\.\d{1,2})?$/.test(value)) return null;
  const [whole = "0", fraction = ""] = value.split(".");
  return `${BigInt(whole)}.${fraction.padEnd(2, "0")}`;
}
export function cents(value: string): bigint {
  const normalized = normalizeMoney(value);
  if (!normalized) throw new Error("Некорректная денежная строка");
  return BigInt(normalized.replace(".", ""));
}
export function money(value: string | null | undefined): string {
  if (value === null || value === undefined || !/^-?\d+(\.\d+)?$/.test(value))
    return "Нет данных";
  const negative = value.startsWith("-");
  const [whole = "0", fraction = ""] = value.replace("-", "").split(".");
  return `${negative ? "−" : ""}${new Intl.NumberFormat("ru-RU").format(BigInt(whole))}${fraction && fraction !== "00" ? `,${fraction}` : ""} ₽`;
}
export function rate(value: string) {
  return `${value
    .replace(/\.0+$/, "")
    .replace(/(\.\d*?)0+$/, "$1")
    .replace(".", ",")}%`;
}
export function date(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Europe/Moscow",
      }).format(new Date(value))
    : "Нет данных";
}
export function elapsed(value: string) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 60000),
  );
  if (minutes < 1) return "Меньше минуты";
  if (minutes < 60) return `${minutes} мин`;
  if (minutes < 1440)
    return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
  return `${Math.floor(minutes / 1440)} дн`;
}

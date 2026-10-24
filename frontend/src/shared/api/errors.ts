export type NormalizedError = {
  message: string;
  fields: Record<string, string>;
  code?: string;
};
const clean = (value: string) => value.slice(0, 600);
export function normalizeError(value: unknown, status = 0): NormalizedError {
  const defaults: Record<number, string> = {
    0: "Не удалось получить ответ. Проверьте соединение и состояние заявки перед повтором.",
    403: "Нет доступа: проверьте сессию, полномочия и CSRF.",
    404: "Данные не найдены или недоступны для вашей учётной записи.",
    409: "Данные изменились. Карточка обновлена; проверьте условия перед новым действием.",
    429: "Слишком много запросов. Дождитесь окончания паузы.",
    503: "Сервис временно недоступен. Действие могло завершиться; сначала обновите данные.",
  };
  const fallback =
    defaults[status] ??
    "Не удалось выполнить запрос. Попробуйте обновить данные.";
  if (status >= 500 || status === 0) return { message: fallback, fields: {} };
  const messages = (input: unknown): string[] =>
    typeof input === "string"
      ? [clean(input)]
      : Array.isArray(input)
        ? input.flatMap(messages).slice(0, 10)
        : [];
  if (Array.isArray(value))
    return { message: messages(value).join(" ") || fallback, fields: {} };
  if (!value || typeof value !== "object")
    return { message: fallback, fields: {} };
  const data = value as Record<string, unknown>;
  const fields: Record<string, string> = Object.create(null) as Record<
    string,
    string
  >;
  for (const [key, field] of Object.entries(data)) {
    if (
      [
        "detail",
        "code",
        "non_field_errors",
        "__proto__",
        "constructor",
      ].includes(key)
    )
      continue;
    const text = messages(field).join(" ");
    if (text) fields[key] = text;
  }
  return {
    message:
      messages(data.detail).concat(messages(data.non_field_errors)).join(" ") ||
      (Object.keys(fields).length ? "Проверьте отмеченные поля." : fallback),
    fields,
    code: typeof data.code === "string" ? clean(data.code) : undefined,
  };
}

export class ApiError extends Error {
  readonly normalized: NormalizedError;
  constructor(
    readonly status: number,
    body: unknown,
    readonly retryAfter = 0,
  ) {
    const result = normalizeError(body, status);
    super(result.message);
    this.name = "ApiError";
    this.normalized = result;
  }
  get uncertain() {
    return this.status === 0 || this.status >= 500;
  }
}

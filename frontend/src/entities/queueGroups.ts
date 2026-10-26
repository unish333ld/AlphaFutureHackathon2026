import type { Schema } from "../shared/api/client";

type Row = Schema["StaffApplicationList"];
export function groupQueue(rows: Row[], ordering: string, now = new Date()) {
  const field = ordering.replace(/^-/, "");
  if (!["created_at", "updated_at", "assigned_at"].includes(field))
    return [{ key: "ordered", label: "", rows }];
  const day = (date: Date) =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Moscow",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  const today = day(now),
    yesterday = day(new Date(now.getTime() - 86400000));
  const groups: { key: string; label: string; rows: Row[] }[] = [];
  for (const row of rows) {
    const value = row[field as "created_at" | "updated_at" | "assigned_at"];
    const key = value ? day(new Date(value)) : "none";
    const date = value ? new Date(value) : null;
    const caption = date
      ? new Intl.DateTimeFormat("ru-RU", {
          timeZone: "Europe/Moscow",
          day: "numeric",
          month: "long",
          ...(key !== today && key !== yesterday
            ? { year: "numeric" as const }
            : {}),
        }).format(date)
      : "Без назначения";
    const label =
      key === today
        ? `Сегодня, ${caption}`
        : key === yesterday
          ? `Вчера, ${caption}`
          : caption;
    const last = groups.at(-1);
    if (last?.key === key) last.rows.push(row);
    else groups.push({ key, label, rows: [row] });
  }
  return groups;
}

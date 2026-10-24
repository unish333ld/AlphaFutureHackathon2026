import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useScope } from "../app/queries";
import { api, type Schema } from "../shared/api/client";
import { Badge } from "../shared/ui/kit";
import { date, currentRevision, money } from "../entities/credit";
import s from "../app/layout.module.css";

export function LoanRows({ rows }: { rows: Schema["ApplicationList"][] }) {
  const scope = useScope();
  const details = useQueries({
    queries: rows.map((row) => ({
      queryKey: [...scope, "application", row.id],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api.application(row.id, false, signal),
      staleTime: 15000,
    })),
  });
  return (
    <div>
      {rows.map((row, index) => {
        const detail = details[index]?.data;
        const revision = detail ? currentRevision(detail) : null;
        const action = detail
          ? [
              "provide_information",
              "sign_agreement",
              "accept_offer",
              "update_draft",
            ]
              .map((name) =>
                detail.available_actions.find(
                  (item) => item.action === name && item.allowed,
                ),
              )
              .find(Boolean)
          : undefined;
        const actionLabel =
          action?.action === "provide_information"
            ? "Ответить банку"
            : action?.action === "update_draft"
              ? "Продолжить"
              : action?.action === "sign_agreement"
                ? "Подписать"
                : action?.action === "accept_offer"
                  ? "Посмотреть условия"
                  : "Открыть заявку";
        const href =
          action?.action === "update_draft"
            ? `/app/loans/${row.id}/edit`
            : `/app/loans/${row.id}/`;
        return (
          <Link
            key={row.id}
            to={href}
            className={s.rowLink}
            aria-label={`${detail?.number ?? row.product_name} · ${row.company_name} · ${actionLabel}`}
          >
            <div>
              <strong>{detail?.number ?? row.product_name}</strong>
              <p>{row.company_name}</p>
              <span className={s.muted}>
                {revision
                  ? `${money(revision.amount)} · ${revision.term_months} мес. · ${row.product_name}`
                  : details[index]?.isError
                    ? "Параметры недоступны — откройте карточку"
                    : "Загружаем параметры…"}
              </span>
              <p>Изменена {date(detail?.updated_at ?? row.updated_at)}</p>
            </div>
            <div className={s.stack} style={{ gap: 10 }}>
              <Badge status={detail?.status ?? row.status} />
              <span className={s.link}>
                {actionLabel} <span aria-hidden="true">→</span>
              </span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

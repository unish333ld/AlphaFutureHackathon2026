import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useScope } from "../app/queries";
import { api, type QueueFilters, type Status } from "../shared/api/client";
import { date, elapsed, money, riskLabels, statuses } from "../entities/credit";
import {
  Badge,
  Button,
  Choice,
  Empty,
  ErrorNotice,
  Input,
  Loading,
  Pagination,
  Panel,
} from "../shared/ui/kit";
import { PageTitle } from "../shared/ui/PageTitle";
import s from "../app/layout.module.css";
import q from "./queue.module.css";

export default function QueuePage() {
  const scope = useScope("bank");
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const storedSearch = params.get("search") ?? "";
  useEffect(() => setSearch(storedSearch), [storedSearch]);
  const assignment = ["all", "free", "mine"].includes(
    params.get("assignment") ?? "",
  )
    ? (params.get("assignment") as "all" | "free" | "mine")
    : "all";
  const status =
    params.get("status") && params.get("status")! in statuses
      ? (params.get("status") as Status)
      : undefined;
  const risk = params.get("risk_level") as QueueFilters["risk_level"];
  const ordering = (params.get("ordering") ??
    "-created_at") as QueueFilters["ordering"];
  const page = Math.max(1, Number(params.get("page")) || 1);
  const filters: QueueFilters = {
    assignment,
    status,
    risk_level: risk || undefined,
    ordering,
    page,
    search: params.get("search") || undefined,
  };
  function update(key: string, value: string) {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      next.delete("page");
      return next;
    });
  }
  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== (params.get("search") ?? "")) update("search", search);
    }, 350);
    return () => clearTimeout(timer);
  }, [search, params]);
  const result = useQuery({
    queryKey: [...scope, "queue", filters],
    queryFn: ({ signal }) => api.queue(filters, signal),
  });
  function clear() {
    setSearch("");
    setParams({});
  }
  const filtered = assignment !== "all" || !!status || !!risk || !!search;
  return (
    <>
      <PageTitle
        title="Очередь заявок"
        subtitle="Назначения, проверки и решения — в едином кредитном процессе."
        eyebrow="Кабинет специалиста"
      />
      <div className={s.chips} aria-label="Фильтр по исполнителю">
        {[
          ["all", "Все"],
          ["free", "Свободные"],
          ["mine", "Мои"],
        ].map(([key, label]) => (
          <Button
            key={key}
            size={40}
            view={assignment === key ? "accent" : "secondary"}
            aria-pressed={assignment === key}
            onClick={() => update("assignment", key ?? "all")}
          >
            {label}
          </Button>
        ))}
      </div>
      <p className={s.muted}>
        {assignment === "free"
          ? "Все без исполнителя, включая завершённые. Выберите статус для рабочей очереди."
          : assignment === "mine"
            ? "Заявки, назначенные вам. Завершённые заявки остаются в общей очереди и истории."
            : "Риск и параметры относятся к актуальной ревизии. Время в состоянии — фактическое, без банковского SLA."}
      </p>
      <div className={q.filters}>
        <Input
          label="Поиск по номеру, компании или ИНН"
          labelView="outer"
          value={search}
          onChange={(_, { value }) => setSearch(value)}
          maxLength={100}
          block
        />
        <Choice
          label="Статус"
          value={status ?? ""}
          onChange={(value) => update("status", value)}
          options={[
            { key: "", content: "Все состояния" },
            ...Object.entries(statuses).map(([key, content]) => ({
              key,
              content,
            })),
          ]}
        />
        <Choice
          label="Риск"
          value={risk ?? ""}
          onChange={(value) => update("risk_level", value)}
          options={[
            { key: "", content: "Любой риск" },
            { key: "unassessed", content: "Без оценки" },
            ...Object.entries(riskLabels).map(([key, content]) => ({
              key,
              content,
            })),
          ]}
        />
        <Choice
          label="Сортировка"
          value={ordering ?? "-created_at"}
          onChange={(value) => update("ordering", value)}
          options={[
            { key: "-created_at", content: "Сначала новые" },
            { key: "created_at", content: "Сначала ранние" },
            { key: "-updated_at", content: "Недавно изменённые" },
            { key: "-amount", content: "По сумме ↓" },
            { key: "amount", content: "По сумме ↑" },
            { key: "number", content: "По номеру" },
            { key: "-assigned_at", content: "По назначению" },
            { key: "term_months", content: "По сроку" },
          ]}
        />
        <Button
          onClick={() => {
            void result.refetch();
          }}
          disabled={result.isFetching}
          size={48}
        >
          Обновить
        </Button>
      </div>
      <Panel>
        {result.isPending ? (
          <Loading />
        ) : result.isError ? (
          <ErrorNotice
            error={result.error}
            retry={() => {
              void result.refetch();
            }}
          />
        ) : !result.data.count ? (
          <Empty
            title={
              filtered
                ? "По выбранным условиям заявок нет"
                : "Очередь пока пуста"
            }
            action={
              <Button
                onClick={
                  filtered
                    ? clear
                    : () => {
                        void result.refetch();
                      }
                }
              >
                {filtered ? "Сбросить фильтры" : "Обновить очередь"}
              </Button>
            }
          >
            {filtered
              ? "Измените условия поиска или покажите все заявки."
              : "Отправленные клиентами заявки появятся здесь."}
          </Empty>
        ) : (
          <>
            <div className={q.tableWrap}>
              <table className={q.table}>
                <caption className={q.caption}>Кредитные заявки</caption>
                <thead>
                  <tr>
                    <th scope="col">Заявка и компания</th>
                    <th scope="col">Сумма и продукт</th>
                    <th scope="col">Риск</th>
                    <th scope="col">Статус</th>
                    <th scope="col">Исполнитель</th>
                    <th scope="col">В состоянии</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.results.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <Link
                          to={`/staff/applications/${row.id}`}
                          className={q.number}
                        >
                          {row.number}
                        </Link>
                        <strong className={q.company}>
                          {row.company_name}
                        </strong>
                        <span className={q.small}>ИНН {row.company_inn}</span>
                      </td>
                      <td>
                        <strong>{money(row.amount)}</strong>
                        <span className={q.small}>
                          {row.term_months === null
                            ? "Нет срока"
                            : `${row.term_months} мес.`}
                        </span>
                        <span className={q.small}>{row.product_name}</span>
                      </td>
                      <td>
                        <span
                          className={`${q.risk} ${row.risk_level ? q[row.risk_level] : ""}`}
                        >
                          {row.risk_level
                            ? riskLabels[row.risk_level]
                            : "Нет оценки"}
                        </span>
                      </td>
                      <td>
                        <Badge status={row.status} />
                      </td>
                      <td>
                        <span>
                          {row.assigned_to
                            ? row.assigned_to.first_name ||
                              row.assigned_to.username
                            : "Не назначен"}
                        </span>
                        {row.assigned_at ? (
                          <span className={q.small}>
                            {date(row.assigned_at)}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <span>{elapsed(row.status_changed_at)}</span>
                        <span className={q.small}>
                          {date(row.status_changed_at)}
                        </span>
                        <Link
                          to={`/staff/applications/${row.id}`}
                          className={s.link}
                        >
                          Открыть →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={q.mobileRows}>
              {result.data.results.map((row) => (
                <Link
                  className={q.mobileCard}
                  key={row.id}
                  to={`/staff/applications/${row.id}`}
                >
                  <div className={s.summaryRow}>
                    <strong className={q.number}>{row.number}</strong>
                    <Badge status={row.status} />
                  </div>
                  <h3>{row.company_name}</h3>
                  <p className={s.muted}>ИНН {row.company_inn}</p>
                  <strong>
                    {money(row.amount)}, {row.term_months ?? "—"} мес.
                  </strong>
                  <p className={s.muted}>{row.product_name}</p>
                  <div className={s.summaryRow}>
                    <span>
                      Риск:{" "}
                      {row.risk_level
                        ? riskLabels[row.risk_level]
                        : "Нет оценки"}
                    </span>
                    <span>{row.assigned_to?.username ?? "Не назначен"}</span>
                  </div>
                  <p className={s.muted}>
                    В состоянии: {elapsed(row.status_changed_at)}
                  </p>
                  <span className={s.link}>Открыть карточку →</span>
                </Link>
              ))}
            </div>
            <Pagination
              {...result.data}
              page={page}
              length={result.data.results.length}
              onPage={(next) =>
                setParams((prev) => {
                  const value = new URLSearchParams(prev);
                  value.set("page", String(next));
                  return value;
                })
              }
            />
          </>
        )}
      </Panel>
    </>
  );
}

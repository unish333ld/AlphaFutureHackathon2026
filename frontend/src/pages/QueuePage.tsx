import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useScope } from "../app/queries";
import { api, type QueueFilters, type Status } from "../shared/api/client";
import {
  displayName,
  elapsed,
  money,
  riskLabels,
  statuses,
} from "../entities/credit";
import { groupQueue } from "../entities/queueGroups";
import { ApiError } from "../shared/api/errors";
import {
  Badge,
  Button,
  Choice,
  Empty,
  ErrorNotice,
  Input,
  Loading,
  Pagination,
} from "../shared/ui/kit";
import { PageTitle } from "../shared/ui/PageTitle";
import s from "../app/layout.module.css";
import q from "./queue.module.css";

export default function QueuePage() {
  const scope = useScope("bank");
  const [params, setParams] = useSearchParams();
  const storedSearch = params.get("search") ?? "";
  const [search, setSearch] = useState(storedSearch);
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
    search: storedSearch || undefined,
  };
  function update(key: string, value: string) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      if (value) next.set(key, value);
      else next.delete(key);
      next.delete("page");
      return next;
    });
  }
  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== storedSearch) update("search", search);
    }, 350);
    return () => clearTimeout(timer);
  }, [search, storedSearch]);
  const result = useQuery({
    queryKey: [...scope, "queue", filters],
    queryFn: ({ signal }) => api.queue(filters, signal),
    refetchInterval: 10000,
  });
  useEffect(() => {
    if (
      page > 1 &&
      result.error instanceof ApiError &&
      result.error.status === 404
    )
      update("page", "");
  }, [page, result.error]);
  const filtered = assignment !== "all" || !!status || !!risk || !!search;
  const groups = groupQueue(
    result.data?.results ?? [],
    ordering ?? "-created_at",
  );
  return (
    <>
      <PageTitle
        title="Очередь заявок"
        subtitle="Найдите заявку и возьмите её в работу."
        eyebrow="Кабинет специалиста"
      />
      <div className={s.chips} aria-label="Фильтр по исполнителю">
        {(
          [
            ["all", "Все"],
            ["free", "Свободные"],
            ["mine", "Мои"],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            size={40}
            view={assignment === key ? "accent" : "secondary"}
            aria-pressed={assignment === key}
            onClick={() => update("assignment", key)}
          >
            {label}
          </Button>
        ))}
      </div>
      <p className={s.muted}>
        {assignment === "free"
          ? "Заявки без исполнителя. Для работы выберите нужный статус."
          : assignment === "mine"
            ? "Заявки, назначенные вам."
            : "Все заявки доступных компаний."}
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
            { key: "", content: "Все статусы" },
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
            { key: "-amount", content: "Сумма по убыванию" },
            { key: "amount", content: "Сумма по возрастанию" },
            { key: "number", content: "По номеру" },
            { key: "-assigned_at", content: "По дате назначения" },
            { key: "term_months", content: "По сроку" },
          ]}
        />
      </div>
      {result.isPending ? (
        <Loading />
      ) : result.isError ? (
        <ErrorNotice error={result.error} retry={() => void result.refetch()} />
      ) : !result.data.count ? (
        <Empty
          title={
            filtered ? "По выбранным условиям заявок нет" : "Очередь пока пуста"
          }
          action={
            filtered ? (
              <Button
                onClick={() => {
                  setSearch("");
                  setParams({});
                }}
              >
                Сбросить фильтры
              </Button>
            ) : undefined
          }
        >
          {filtered
            ? "Измените условия поиска."
            : "Отправленные заявки появятся здесь."}
        </Empty>
      ) : (
        <>
          <div className={q.groups}>
            {groups.map((group) => (
              <section
                key={group.key}
                aria-label={group.label || "Заявки в выбранном порядке"}
              >
                {group.label ? (
                  <h2 className={q.dateHeading}>{group.label}</h2>
                ) : null}
                <ul className={q.cards}>
                  {group.rows.map((row, index) => (
                    <li
                      key={row.id}
                      className={
                        (index + 1) % 4 === 0 && index < group.rows.length - 1
                          ? q.breath
                          : undefined
                      }
                    >
                      <Link
                        to={`/staff/applications/${row.id}`}
                        className={q.card}
                        aria-label={`Заявка ${row.number}, ${displayName(row.company_name)}`}
                      >
                        <div className={q.identity}>
                          <strong className={q.number}>{row.number}</strong>
                          <strong>{displayName(row.company_name)}</strong>
                          <span className={s.muted}>ИНН {row.company_inn}</span>
                        </div>
                        <div>
                          <span className={q.label}>Сумма и срок</span>
                          <strong>{money(row.amount)}</strong>
                          <span>
                            {row.term_months === null
                              ? "Срок не указан"
                              : `${row.term_months} мес.`}
                          </span>
                          <span className={s.muted}>
                            {displayName(row.product_name)}
                          </span>
                        </div>
                        <div>
                          <span className={q.label}>Оценка риска</span>
                          <span
                            className={`${q.risk} ${row.risk_level ? q[row.risk_level] : ""}`}
                          >
                            {row.risk_level
                              ? riskLabels[row.risk_level]
                              : "Нет оценки"}
                          </span>
                        </div>
                        <div>
                          <span className={q.label}>Статус</span>
                          <Badge status={row.status} />
                        </div>
                        <div>
                          <span className={q.label}>Исполнитель</span>
                          <span>
                            {row.assigned_to?.first_name ||
                              row.assigned_to?.username ||
                              "Не назначен"}
                          </span>
                          <span className={s.muted}>
                            В текущем статусе {elapsed(row.status_changed_at)}
                          </span>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <Pagination
            {...result.data}
            page={page}
            pageSize={10}
            length={result.data.results.length}
            onPage={(next) => {
              setParams((previous) => {
                const value = new URLSearchParams(previous);
                value.set("page", String(next));
                return value;
              });
              window.scrollTo({ top: 0, behavior: "instant" });
            }}
          />
        </>
      )}
    </>
  );
}

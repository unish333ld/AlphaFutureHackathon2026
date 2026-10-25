import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../app/auth";
import { useScope } from "../app/queries";
import { api } from "../shared/api/client";
import { date } from "../entities/credit";
import {
  Empty,
  ErrorNotice,
  Loading,
  Pagination,
  Panel,
} from "../shared/ui/kit";
import d from "./detail.module.css";

const labels: Record<string, string> = {
  created: "Создан черновик",
  draft_updated: "Черновик изменён",
  submitted: "Отправлена ревизия",
  checks_started: "Начаты проверки",
  checks_error: "Техническая ошибка проверки",
  information_requested: "Запрошены дополнительные сведения",
  checks_completed: "Проверки завершены",
  offered: "Подготовлено предложение",
  rejected: "Отказ по серверным правилам",
  expired: "Истёк срок предложения или подписи",
  offer_declined: "Клиент отклонил предложение",
  offer_accepted: "Клиент принял предложение",
  signed: "Сохранена условная подпись",
  issued: "Выполнена моделируемая выдача",
  assignment_claimed: "Назначен исполнитель",
  assignment_released: "Назначение освобождено",
};
export function History({ id }: { id: string }) {
  const scope = useScope();
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const result = useQuery({
    queryKey: [...scope, "events", id, page],
    queryFn: ({ signal }) => api.events(id, page, signal),
  });
  return (
    <Panel title="История заявки">
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
        <Empty title="Событий пока нет" />
      ) : (
        <>
          <ol className={d.timeline}>
            {result.data.results.map((event) => (
              <li key={event.id}>
                <time dateTime={event.created_at}>
                  {date(event.created_at)}
                </time>
                <div>
                  <strong>
                    {labels[event.event_type] ?? "Изменение заявки"}
                  </strong>
                  <p>
                    {event.actor === user?.id
                      ? "Вы"
                      : event.actor
                        ? "Участник процесса"
                        : "Система"}
                    {event.details.revision_no
                      ? `, ревизия ${event.details.revision_no}`
                      : ""}
                    {event.details.attempt
                      ? `, попытка ${event.details.attempt}`
                      : ""}
                    {event.details.reason === "terminal_state"
                      ? ", заявка завершена"
                      : ""}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <Pagination
            {...result.data}
            page={page}
            length={result.data.results.length}
            onPage={setPage}
          />
        </>
      )}
    </Panel>
  );
}

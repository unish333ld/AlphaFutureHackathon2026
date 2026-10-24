import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useScope } from "../app/queries";
import { api, type Status } from "../shared/api/client";
import { statuses } from "../entities/credit";
import {
  Button,
  Choice,
  Empty,
  ErrorNotice,
  Loading,
  Pagination,
  Panel,
} from "../shared/ui/kit";
import { LinkButton } from "../shared/ui/navigation";
import { PageTitle } from "../shared/ui/PageTitle";
import { LoanRows } from "../features/LoanRows";
import s from "../app/layout.module.css";

export default function LoansPage() {
  const scope = useScope();
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const rawStatus = params.get("status") ?? "";
  const status = rawStatus in statuses ? (rawStatus as Status) : undefined;
  const list = useQuery({
    queryKey: [...scope, "applications", page, status ?? "all"],
    queryFn: ({ signal }) => api.applications(page, status, signal),
  });
  function change(value: string) {
    setParams(value ? { status: value } : {});
  }
  return (
    <>
      <PageTitle
        title="Заявки и кредиты"
        subtitle="Черновики, рассмотрение, предложения и моделируемые выдачи всех доступных компаний."
        action={
          <LinkButton to="/app/loans/new" view="accent">
            + Новая заявка
          </LinkButton>
        }
      />
      <div className={s.inline} style={{ marginBottom: 24 }}>
        <div style={{ minWidth: 240, maxWidth: "100%" }}>
          <Choice
            label="Статус заявки"
            value={status ?? ""}
            onChange={change}
            options={[
              { key: "", content: "Все состояния" },
              ...Object.entries(statuses).map(([key, content]) => ({
                key,
                content,
              })),
            ]}
          />
        </div>
        <Button
          size={40}
          onClick={() => {
            void list.refetch();
          }}
          disabled={list.isFetching}
        >
          Обновить
        </Button>
      </div>
      <Panel>
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <ErrorNotice
            error={list.error}
            retry={() => {
              void list.refetch();
            }}
          />
        ) : !list.data.count ? (
          <Empty
            title={
              status
                ? "Заявок с таким статусом нет"
                : "У вас пока нет заявок и кредитов"
            }
            action={
              status ? (
                <Button onClick={() => change("")}>Сбросить фильтр</Button>
              ) : (
                <LinkButton to="/app/loans/new" view="accent">
                  + Новая заявка
                </LinkButton>
              )
            }
          >
            {status
              ? "Попробуйте выбрать другое состояние или показать все заявки."
              : "Выберите задачу на главной или создайте новую заявку."}
          </Empty>
        ) : (
          <>
            <LoanRows rows={list.data.results} />
            <Pagination
              {...list.data}
              page={page}
              length={list.data.results.length}
              onPage={(next) =>
                setParams({ ...(status ? { status } : {}), page: String(next) })
              }
            />
          </>
        )}
      </Panel>
    </>
  );
}

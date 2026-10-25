import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useCatalogs, useScope } from "../app/queries";
import { api } from "../shared/api/client";
import {
  Choice,
  Empty,
  ErrorNotice,
  Facts,
  Loading,
  Notice,
  Panel,
} from "../shared/ui/kit";
import { PageTitle } from "../shared/ui/PageTitle";
import { LinkButton } from "../shared/ui/navigation";
import { LoanRows } from "../features/LoanRows";
import { money, rate } from "../entities/credit";
import s from "../app/layout.module.css";

export default function HomePage() {
  const { user } = useAuth();
  const scope = useScope();
  const { companies, products } = useCatalogs();
  const [companyId, setCompanyId] = useState("");
  const list = useQuery({
    queryKey: [...scope, "applications", 1, "all"],
    queryFn: ({ signal }) => api.applications(1, undefined, signal),
  });
  const company =
    companies.data?.find((item) => item.id === companyId) ??
    companies.data?.[0];
  const selected = company?.id ?? "";
  return (
    <div className={s.stack}>
      <PageTitle
        title={`Здравствуйте${user ? `, ${user.first_name || user.username}` : ""}`}
        subtitle="Что сегодня нужно вашему бизнесу?"
        eyebrow="Кабинет предпринимателя"
      />
      {list.data?.results.some((row) => row.status === "needs_info") ? (
        <Notice tone="warning" title="Банк запросил дополнительные сведения">
          <div className={s.summaryRow}>
            <span>В одной из последних заявок нужен ваш ответ.</span>
            <LinkButton
              to={`/app/loans/${list.data.results.find((row) => row.status === "needs_info")?.id}/`}
            >
              Посмотреть запрос
            </LinkButton>
          </div>
        </Notice>
      ) : null}
      <Panel title="Нужны деньги на бизнес?" className={s.highlightPanel}>
        <p className={s.muted}>
          Выберите задачу. Параметры и финансовые показатели можно проверить
          перед отправкой.
        </p>
        {products.isPending ? (
          <Loading />
        ) : products.isError ? (
          <ErrorNotice
            error={products.error}
            retry={() => {
              void products.refetch();
            }}
          />
        ) : !products.data.length ? (
          <Empty title="Продукты пока недоступны" />
        ) : (
          <div className={s.tiles}>
            {products.data.map((product) => (
              <Link
                className={s.tile}
                to={`/app/loans/new?product=${product.id}&company=${selected}`}
                key={product.id}
              >
                <span className={s.tileIcon} aria-hidden="true">
                  {product.code === "equipment" ? "⚙" : "↗"}
                </span>
                <h3>{product.name}</h3>
                <p>{product.description}</p>
                <strong>
                  {money(product.min_amount)} — {money(product.max_amount)}
                </strong>
                <p>
                  {product.min_term_months}–{product.max_term_months} мес.,
                  базовая ставка демо {rate(product.annual_rate)}
                </p>
                <span className={s.link}>Создать заявку →</span>
              </Link>
            ))}
          </div>
        )}
      </Panel>
      <div className={s.columns}>
        <Panel
          title="Последние заявки"
          action={
            <Link to="/app/loans" className={s.link}>
              Все заявки →
            </Link>
          }
        >
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
              title="Заявок пока нет"
              action={
                <LinkButton to="/app/loans/new" view="accent">
                  Новая заявка
                </LinkButton>
              }
            >
              Выберите продукт и начните с параметров бизнеса.
            </Empty>
          ) : (
            <>
              <p className={s.muted}>
                Последние {Math.min(6, list.data.results.length)} заявок
                доступных вам компаний.
              </p>
              <LoanRows rows={list.data.results.slice(0, 6)} />
            </>
          )}
        </Panel>
        <Panel title="Данные компании">
          {companies.isPending ? (
            <Loading />
          ) : companies.isError ? (
            <ErrorNotice
              error={companies.error}
              retry={() => {
                void companies.refetch();
              }}
            />
          ) : !company ? (
            <Empty title="Нет доступных компаний">
              Проверьте членство и полномочия вашей учётной записи.
            </Empty>
          ) : (
            <div className={s.stack}>
              <Choice
                label="Компания для новой заявки"
                value={selected}
                onChange={setCompanyId}
                options={companies.data.map((item) => ({
                  key: item.id,
                  content: item.name,
                }))}
              />
              <Facts
                rows={[
                  { label: "ИНН", value: company.inn },
                  {
                    label: "Форма",
                    value:
                      company.kind === "legal"
                        ? "Юридическое лицо"
                        : "Индивидуальный предприниматель",
                  },
                  {
                    label: "Дата регистрации",
                    value: company.registered_at.split("-").reverse().join("."),
                  },
                  {
                    label: "Статус",
                    value:
                      company.status === "active"
                        ? "Действующая"
                        : "Неактивная",
                  },
                ]}
              />
              <p className={s.muted}>
                Сведения получены из синтетического профиля. Финансовые
                показатели вы укажете в заявке.
              </p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

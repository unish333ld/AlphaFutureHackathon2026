import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useApplication, useScope } from "../app/queries";
import { api, type Application } from "../shared/api/client";
import {
  actionFor,
  displayName,
  checkLabels,
  checkStatuses,
  currentAssessment,
  currentOffer,
  currentRevision,
  date,
  money,
  rate,
  riskLabels,
} from "../entities/credit";
import {
  Badge,
  ErrorNotice,
  Facts,
  Loading,
  Notice,
  Panel,
} from "../shared/ui/kit";
import { PageTitle } from "../shared/ui/PageTitle";
import { ApplicationActions } from "../features/ApplicationActions";
import { History } from "../features/History";
import { Schedule } from "../features/Schedule";
import { AgreementSummary } from "../features/AgreementSummary";
import { IssuanceFeedback } from "../features/CompletionFeedback";
import { CreditCost, OfferComparison } from "../features/CreditDisclosure";
import { ReadinessChecklist } from "../features/ReadinessChecklist";
import s from "../app/layout.module.css";
import d from "../features/detail.module.css";

export default function ApplicationRoute() {
  const { id } = useParams();
  return <ApplicationPage key={id} id={id ?? ""} />;
}
function ApplicationPage({ id }: { id: string }) {
  const query = useApplication(id);
  const { user } = useAuth();
  const cache = useQueryClient();
  useEffect(() => {
    if (query.dataUpdatedAt && user)
      void cache.invalidateQueries({
        queryKey: ["user", user.id],
        predicate: (item) =>
          item.queryKey.includes("queue") ||
          item.queryKey.includes("applications"),
        refetchType: "none",
      });
  }, [query.dataUpdatedAt, cache, user]);
  if (query.isPending) return <Loading />;
  if (!query.data)
    return (
      <ErrorNotice
        error={query.error}
        retry={() => {
          void query.refetch();
        }}
      />
    );
  return (
    <>
      {query.isError ? (
        <ErrorNotice
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      ) : null}
      <ApplicationContent
        app={query.data}
        refresh={async () => {
          const result = await query.refetch();
          return result.isSuccess ? result.data : undefined;
        }}
      />
    </>
  );
}
function ApplicationContent({
  app,
  refresh,
}: {
  app: Application;
  refresh: () => Promise<Application | undefined>;
}) {
  const { user } = useAuth();
  const scope = useScope(app.company);
  const staff = user?.system_role === "specialist";
  const company = useQuery({
    queryKey: [...scope, "company", app.company],
    queryFn: ({ signal }) => api.company(app.company, signal),
    staleTime: 60000,
  });
  const revision = currentRevision(app);
  const assessment = currentAssessment(revision);
  const decision =
    assessment?.decision?.assessment === assessment?.id
      ? assessment?.decision
      : null;
  const offer = currentOffer(app);
  const agreement = offer?.agreement;
  const attempt = revision
    ? Math.max(0, ...revision.checks.map((check) => check.attempt))
    : 0;
  const checks =
    revision?.checks.filter((check) => check.attempt === attempt) ?? [];
  return (
    <div className={s.stack}>
      <div className={s.breadcrumb}>
        <Link to={staff ? "/staff" : "/app/loans"}>
          {staff ? "Очередь" : "Заявки и кредиты"}
        </Link>
        <span>/</span>
        <span>{app.number}</span>
      </div>
      <PageTitle
        title={`Заявка ${app.number}`}
        subtitle={displayName(app.company_name)}
      />
      <div className={s.inline}>
        <Badge status={app.status} />
        <span className={s.muted}>Изменена {date(app.updated_at)}</span>
      </div>
      <IssuanceFeedback app={app} />
      {!revision ? (
        <Notice tone="error" title="Данные заявки недоступны">
          Не удалось показать актуальные сведения. Попробуйте открыть заявку
          позже.
        </Notice>
      ) : (
        <div className={d.detailGrid}>
          <div className={s.stack}>
            <Panel title="Запрос клиента">
              <div className={s.summaryRow}>
                <div>
                  <p className={s.muted}>Запрошенная сумма</p>
                  <div className={s.bigAmount}>{money(revision.amount)}</div>
                </div>
                <div>
                  <p className={s.muted}>Срок</p>
                  <strong style={{ fontSize: 24 }}>
                    {revision.term_months} мес.
                  </strong>
                </div>
              </div>
              <hr className={s.rule} />
              <Facts
                rows={[
                  { label: "Продукт", value: displayName(app.product_name) },
                  { label: "Цель", value: revision.purpose },
                  ...(staff
                    ? [{ label: "Версия заявки", value: revision.revision_no }]
                    : []),
                  { label: "Отправлена", value: date(revision.submitted_at) },
                ]}
              />
            </Panel>
            <Panel title="О компании">
              {company.isPending ? (
                <Loading />
              ) : company.isError ? (
                <ErrorNotice
                  error={company.error}
                  retry={() => {
                    void company.refetch();
                  }}
                />
              ) : (
                <Facts
                  rows={[
                    {
                      label: "Название",
                      value: displayName(company.data.name),
                    },
                    { label: "ИНН", value: company.data.inn },
                    {
                      label: "Регистрация",
                      value: company.data.registered_at
                        .split("-")
                        .reverse()
                        .join("."),
                    },
                    {
                      label: "Статус",
                      value:
                        company.data.status === "active"
                          ? "Действующая"
                          : "Неактивная",
                    },
                    {
                      label: "Клиент банка",
                      value: company.data.is_existing_client ? "Да" : "Нет",
                    },
                  ]}
                />
              )}
            </Panel>
            <ReadinessChecklist app={app} staff={staff} />
            <Panel title="Месячные показатели">
              <Facts
                rows={[
                  { label: "Выручка", value: money(revision.monthly_revenue) },
                  { label: "Расходы", value: money(revision.monthly_expenses) },
                  {
                    label: "Платежи по обязательствам",
                    value: money(revision.monthly_debt_payments),
                  },
                ]}
              />
            </Panel>
          </div>
          <div className={s.stack}>
            {revision.information_requests.length ? (
              <Panel title="Проверка введённых данных">
                {revision.information_requests.map((item) => (
                  <div key={item.id} className={s.subtle}>
                    <p>{item.question}</p>
                    <p className={s.muted}>
                      {item.response_revision
                        ? `Ответ получен ${date(item.responded_at)}`
                        : "Ожидается ответ клиента"}
                    </p>
                  </div>
                ))}
              </Panel>
            ) : null}
            <Panel title="Проверки">
              {!checks.length ? (
                <p className={s.muted}>
                  Проверки выполняются после отправки заявки.
                </p>
              ) : (
                <ul className={d.checks}>
                  {checks.map((check) => (
                    <li key={check.id}>
                      <span
                        className={`${d.checkIcon} ${check.status === "passed" ? d.pass : check.status === "failed" ? d.fail : d.warn}`}
                        aria-hidden="true"
                      >
                        {check.status === "passed" ? "✓" : "!"}
                      </span>
                      <div>
                        <strong>{checkLabels[check.kind]}</strong>
                        <p>{checkStatuses[check.status]}</p>
                        <small>{date(check.checked_at)}</small>
                        {"missing_fields" in check.result &&
                        check.result.missing_fields.length ? (
                          <p className={s.muted}>
                            Заполните месячные финансовые показатели.
                          </p>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {checks.some((check) => check.status === "error") ? (
                <Notice tone="warning">
                  Техническая ошибка проверки не является кредитным отказом.
                  Используйте разрешённый повтор.
                </Notice>
              ) : null}
            </Panel>
            <Panel title="Оценка риска">
              {!assessment ? (
                <p className={s.muted}>
                  {revision.assessment
                    ? "Данные изменились. Ожидается новая оценка."
                    : "Оценка пока не готова."}
                </p>
              ) : (
                <>
                  <div className={s.summaryRow}>
                    <strong className={`${d.risk} ${d[assessment.risk_level]}`}>
                      {riskLabels[assessment.risk_level]} риск
                    </strong>
                  </div>
                  <hr className={s.rule} />
                  <Facts
                    rows={[
                      {
                        label: "Операционный поток до платежей по долгам",
                        value: money(assessment.factors.monthly_cashflow),
                      },
                      {
                        label: "Доступный платёж",
                        value: money(assessment.factors.payment_capacity),
                      },
                      {
                        label: "Коэффициент потока",
                        value: assessment.factors.capacity_fraction.replace(
                          ".",
                          ",",
                        ),
                      },
                      {
                        label: "Негативные проверки",
                        value: assessment.factors.failed_checks.length
                          ? assessment.factors.failed_checks
                              .map((kind) => checkLabels[kind])
                              .join(", ")
                          : "Не выявлены",
                      },
                    ]}
                  />
                </>
              )}
            </Panel>
            {decision ? (
              <Panel
                title={
                  decision.outcome === "approved"
                    ? "Запрошенные условия одобрены"
                    : decision.outcome === "counteroffer"
                      ? "Встречное предложение"
                      : "Решение: отказ"
                }
              >
                <Notice
                  tone={decision.outcome === "rejected" ? "warning" : "success"}
                >
                  {decision.explanation}
                </Notice>
                {offer ? (
                  <>
                    <div className={s.bigAmount}>{money(offer.amount)}</div>
                    {decision.outcome === "counteroffer" &&
                    offer.comparison.source_revision_id === revision.id ? (
                      <OfferComparison value={offer.comparison} />
                    ) : null}
                    <Facts
                      rows={[
                        { label: "Ставка", value: rate(offer.annual_rate) },
                        { label: "Срок", value: `${offer.term_months} мес.` },
                        {
                          label: "Платёж в месяц",
                          value: money(offer.monthly_payment),
                        },
                        { label: "Принять до", value: date(offer.expires_at) },
                        ...(offer.sign_before
                          ? [
                              {
                                label: "Подписать до",
                                value: date(offer.sign_before),
                              },
                            ]
                          : []),
                      ]}
                    />
                    <hr className={s.rule} />
                    <CreditCost value={offer.cost_breakdown} />
                    <Schedule schedule={offer.schedule} />
                  </>
                ) : null}
              </Panel>
            ) : null}
          </div>
          <aside className={s.stack}>
            {staff ? (
              <Panel title="Исполнитель">
                <h3>
                  {app.assigned_to
                    ? app.assigned_to.first_name || app.assigned_to.username
                    : "Не назначен"}
                </h3>
                <p className={s.muted}>
                  {app.assigned_at
                    ? `Назначена ${date(app.assigned_at)}`
                    : actionFor(app, "claim")?.allowed
                      ? "Свободную заявку может взять в работу специалист."
                      : "Назначение специалиста в текущем состоянии недоступно."}
                </p>
                {app.assigned_to && app.assigned_to.id !== user?.id ? (
                  <Notice tone="warning">
                    Заявка занята другим специалистом. Переназначение
                    недоступно.
                  </Notice>
                ) : null}
              </Panel>
            ) : null}
            <ApplicationActions app={app} reload={refresh} />
            {agreement ? (
              <AgreementSummary
                app={app}
                agreement={agreement}
                reload={refresh}
              />
            ) : null}
          </aside>
        </div>
      )}
      {staff && app.revisions.length > 1 ? (
        <Panel title="Предыдущие ревизии">
          <details>
            <summary className={s.link}>
              Сохранено версий: {app.revisions.length}
            </summary>
            {app.revisions
              .filter((item) => item.id !== app.current_revision_id)
              .map((item) => (
                <div className={d.oldRevision} key={item.id}>
                  <h3>Версия {item.revision_no}</h3>
                  <p>
                    {money(item.amount)}, {item.term_months} мес.,{" "}
                    {item.purpose}
                  </p>
                  <p className={s.muted}>
                    Отправлена {date(item.submitted_at)}. Эти данные не
                    используются для текущего решения.
                  </p>
                  <ul>
                    {item.checks.map((check) => (
                      <li key={check.id}>
                        {checkLabels[check.kind]}: {checkStatuses[check.status]}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
          </details>
        </Panel>
      ) : null}
      <History id={app.id} version={app.lock_version} />
    </div>
  );
}

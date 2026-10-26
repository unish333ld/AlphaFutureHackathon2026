import { Navigate, useParams } from "react-router-dom";
import { useApplication } from "../app/queries";
import {
  currentRevision,
  displayName,
  money,
  nextSteps,
} from "../entities/credit";
import {
  Badge,
  ErrorNotice,
  Facts,
  Loading,
  Notice,
  Panel,
} from "../shared/ui/kit";
import { LinkButton } from "../shared/ui/navigation";
import { PageTitle } from "../shared/ui/PageTitle";
import s from "../app/layout.module.css";

export default function SubmittedPage() {
  const { id = "" } = useParams();
  const query = useApplication(id);
  if (query.isPending) return <Loading />;
  if (query.isError)
    return (
      <ErrorNotice
        error={query.error}
        retry={() => {
          void query.refetch();
        }}
      />
    );
  const app = query.data;
  const revision = currentRevision(app);
  if (!revision?.submitted_at)
    return <Navigate to={`/app/loans/${id}`} replace />;
  return (
    <div className={s.columns}>
      <Panel>
        <div className={s.eyebrow}>Заявка отправлена</div>
        <PageTitle
          title={`Заявка ${app.number} отправлена`}
          subtitle="Текущий статус и все последующие действия доступны в карточке."
        />
        <Badge status={app.status} />
        <div style={{ margin: "24px 0" }}>
          <Facts
            rows={[
              { label: "Компания", value: displayName(app.company_name) },
              { label: "Продукт", value: displayName(app.product_name) },
              { label: "Сумма", value: money(revision.amount) },
              { label: "Срок", value: `${revision.term_months} мес.` },
            ]}
          />
        </div>
        <Notice
          tone={
            app.status === "checking" || app.status === "needs_info"
              ? "warning"
              : "info"
          }
        >
          {nextSteps[app.status]}
        </Notice>
        <div className={s.actions}>
          <LinkButton to={`/app/loans/${id}`} view="accent">
            Перейти к заявке
          </LinkButton>
          <LinkButton to="/app/loans">Все заявки</LinkButton>
        </div>
      </Panel>
      <Panel title="Что будет дальше">
        <ol className={s.checkList}>
          {[
            "Проверки данных и рассмотрение",
            "Решение и предложение по правилам",
            "Принятие и условное подписание",
            "Моделируемая выдача сотрудником",
          ].map((label, index) => (
            <li key={label}>
              <span className={s.stepDot}>{index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
        <p className={s.muted}>
          Отправка заявки не означает одобрение кредита.
        </p>
      </Panel>
    </div>
  );
}

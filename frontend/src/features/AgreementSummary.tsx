import type { Agreement, Application } from "../shared/api/client";
import { actionFor, money } from "../entities/credit";
import { useAuth } from "../app/auth";
import { Notice, Panel } from "../shared/ui/kit";
import { AgreementDocuments } from "./AgreementDocuments";
import { AgreementSigning } from "./AgreementSigning";
import { Schedule } from "./Schedule";
import a from "./agreementSummary.module.css";

export function AgreementSummary({
  app,
  agreement,
  reload,
}: {
  app: Application;
  agreement: Agreement;
  reload: () => Promise<Application | undefined>;
}) {
  const { user } = useAuth();
  return (
    <Panel title="Договор" className={a.compact}>
      <div className={a.contents}>
        <p className={a.number}>{agreement.number}</p>
        {agreement.disbursement ? (
          <Notice tone="success" title="Выдача завершена">
            <strong>{money(agreement.disbursement.amount)}</strong>
            <p>Операция {agreement.disbursement.id}</p>
          </Notice>
        ) : agreement.signed_at ? (
          <p>Ожидается выдача специалистом.</p>
        ) : (
          <p>Ознакомьтесь с договором перед подписанием.</p>
        )}
        <AgreementDocuments app={app} agreement={agreement} reload={reload} />
        {user?.system_role === "client" ? (
          <AgreementSigning
            app={app}
            reload={reload}
            disabled={!actionFor(app, "sign_agreement")?.allowed}
          />
        ) : null}
        <Schedule schedule={agreement.terms_snapshot.schedule} />
      </div>
    </Panel>
  );
}

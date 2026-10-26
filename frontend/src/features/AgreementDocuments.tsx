import { useRef, useState } from "react";
import { api, type Agreement, type Application } from "../shared/api/client";
import { useAuth } from "../app/auth";
import { Button, ErrorNotice, Notice } from "../shared/ui/kit";
import s from "./agreement.module.css";

export function PdfLinks({
  agreement,
  kind = "original",
}: {
  agreement: Agreement;
  kind?: "original" | "signed_copy";
}) {
  const doc = agreement.documents.find((value) => value.kind === kind);
  if (!doc) return null;
  const url = `/api/v1/agreements/${agreement.id}/pdf/?kind=${kind}`;
  const name = kind === "original" ? "договор" : "подписанную копию";
  return (
    <section aria-label={`PDF: ${name}`} className={s.stack}>
      <div className={s.links}>
        <a href={url} target="_blank" rel="noreferrer">
          Открыть {name} (PDF)
        </a>
        <a href={`${url}&download=true`}>Скачать {name} (PDF)</a>
      </div>
    </section>
  );
}

export function AgreementDocuments({
  app,
  agreement,
  reload,
}: {
  app: Application;
  agreement: Agreement;
  reload: () => Promise<Application | undefined>;
}) {
  const { user } = useAuth();
  const generating = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const capable =
    user?.system_role === "client" &&
    user.memberships.some(
      (membership) =>
        membership.company === app.company &&
        membership.active &&
        membership.can_sign,
    );
  async function generate(signed: boolean) {
    if (generating.current) return;
    generating.current = true;
    setBusy(true);
    setError(null);
    try {
      const fresh = await reload();
      if (!fresh) throw new Error("Не удалось обновить карточку");
      await api.generateDocument(
        agreement.id,
        {
          lock_version: fresh.lock_version,
          document_hash: agreement.document_hash,
        },
        signed,
      );
      await reload();
    } catch (cause) {
      setError(cause);
    } finally {
      generating.current = false;
      setBusy(false);
    }
  }
  const original = agreement.documents.some((doc) => doc.kind === "original");
  const copy = agreement.documents.some((doc) => doc.kind === "signed_copy");
  return (
    <div className={s.stack}>
      {original ? (
        <PdfLinks agreement={agreement} />
      ) : (
        <>
          <p>
            PDF ещё не сформирован. Его создаёт уполномоченный подписант из
            сохранённых условий.
          </p>
          {capable ? (
            <Button
              size={40}
              disabled={busy || app.status === "expired"}
              loading={busy}
              onClick={() => void generate(false)}
            >
              Сформировать PDF-договор
            </Button>
          ) : null}
        </>
      )}
      {agreement.signed_at ? (
        copy ? (
          <PdfLinks agreement={agreement} kind="signed_copy" />
        ) : !agreement.confirmation ? (
          <Notice>
            Эта подпись была смоделирована ранее, без подтверждения кодом. Копия
            с отметкой кода для неё не создаётся; исходные условия не изменены.
          </Notice>
        ) : (
          <>
            <Notice tone="warning">
              Договор подписан. Копия PDF пока недоступна.
            </Notice>
            {capable ? (
              <Button
                size={40}
                disabled={busy}
                loading={busy}
                onClick={() => void generate(true)}
              >
                Повторить создание копии
              </Button>
            ) : null}
          </>
        )
      ) : null}
      {error ? <ErrorNotice error={error} /> : null}
    </div>
  );
}

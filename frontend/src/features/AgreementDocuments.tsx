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
  const [viewer, setViewer] = useState(false);
  const doc = agreement.documents.find((value) => value.kind === kind);
  if (!doc) return null;
  const url = `/api/v1/agreements/${agreement.id}/pdf/?kind=${kind}`;
  const name =
    kind === "original" ? "исходный договор" : "копию с демо-отметкой";
  return (
    <section aria-label={`PDF: ${name}`} className={s.stack}>
      <div className={s.links}>
        <a href={url} target="_blank" rel="noreferrer">
          Открыть {name} (PDF)
        </a>
        <a href={`${url}&download=true`}>Скачать {name} (PDF)</a>
        <Button size={40} onClick={() => setViewer(!viewer)}>
          {viewer ? "Скрыть просмотр PDF" : "Встроенный просмотр PDF"}
        </Button>
      </div>
      {viewer ? (
        <>
          <iframe
            className={s.viewer}
            title={`Просмотр PDF: ${name}`}
            src={url}
          />
          <p>
            Если браузер не поддерживает просмотр PDF, воспользуйтесь ссылками
            открытия и скачивания выше. Финансовые условия и график также
            доступны на странице.
          </p>
        </>
      ) : null}
      <p className={s.hash}>
        Версия {doc.version}. SHA-256 PDF: <code>{doc.pdf_sha256}</code>
      </p>
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
              Подпись сохранена. Копия PDF с отметкой подтверждения пока
              недоступна. Формирование копии не подписывает договор повторно.
            </Notice>
            {capable ? (
              <Button
                size={40}
                disabled={busy}
                loading={busy}
                onClick={() => void generate(true)}
              >
                Сформировать копию с демо-отметкой
              </Button>
            ) : null}
          </>
        )
      ) : null}
      {error ? <ErrorNotice error={error} /> : null}
    </div>
  );
}

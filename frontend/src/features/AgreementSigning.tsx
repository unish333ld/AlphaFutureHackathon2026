import { useEffect, useRef, useState } from "react";
import {
  api,
  type Agreement,
  type Application,
  type Schema,
} from "../shared/api/client";
import { currentOffer, actionFor, reasons } from "../entities/credit";
import { useRefreshCredit } from "../app/queries";
import { ApiError } from "../shared/api/errors";
import {
  Button,
  Checkbox,
  Dialog,
  ErrorNotice,
  Input,
  Notice,
} from "../shared/ui/kit";
import { CreditCost } from "./CreditDisclosure";
import { PdfLinks } from "./AgreementDocuments";
import { CompletionDialog } from "./CompletionFeedback";
import s from "./agreement.module.css";

type Stage = "closed" | "review" | "code" | "sending" | "error";
type Signing = {
  agreement: Agreement;
  app: Application;
  document: Schema["AgreementDocument"];
  attempt?: Schema["SignatureAttempt"];
};

export function AgreementSigning({
  app,
  reload,
  disabled,
}: {
  app: Application;
  reload: () => Promise<Application | undefined>;
  disabled: boolean;
}) {
  const refresh = useRefreshCredit();
  const [stage, setStage] = useState<Stage>("closed");
  const [signing, setSigning] = useState<Signing | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  // A failed card refresh must not erase a successful sign response or invite
  // another signature. Never manufacture a new application lock_version here.
  const [signatureConfirmed, setSignatureConfirmed] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const mounted = useRef(false);
  const run = useRef(0);
  const inFlight = useRef(false);
  const pendingAttempt = useRef<{ agreement: string; attempt: string } | null>(
    null,
  );
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const cancelling = useRef<Promise<void>>(Promise.resolve());
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      run.current++;
      clearTimeout(timer.current);
      const pending = pendingAttempt.current;
      if (pending && !inFlight.current)
        void api
          .cancelSignature(pending.agreement, pending.attempt)
          .catch(() => undefined);
    };
  }, []);
  async function prepare() {
    if (inFlight.current || busy || disabled || signatureConfirmed) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setAcknowledged(false);
    setCode("");
    const token = ++run.current;
    try {
      await cancelling.current;
      const fresh = await reload();
      const agreement = fresh && currentOffer(fresh)?.agreement;
      if (!fresh || !agreement || !actionFor(fresh, "sign_agreement")?.allowed)
        throw new ApiError(409, {
          detail: "Подписание больше недоступно. Проверьте карточку.",
        });
      const document = await api.generateDocument(agreement.id, {
        lock_version: fresh.lock_version,
        document_hash: agreement.document_hash,
      });
      const updated = await api.agreement(agreement.id);
      // Document generation does not change the credit status/version, but does
      // change card metadata. Keep its download links after cancelling review.
      if (mounted.current && run.current === token) await reload();
      if (mounted.current && run.current === token) {
        setSigning({ app: fresh, agreement: updated, document });
        setStage("review");
      }
    } catch (cause) {
      if (mounted.current) setError(cause);
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function begin() {
    if (!signing || !acknowledged || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const token = ++run.current;
    try {
      const attempt = await api.signatureAttempt(signing.agreement.id, {
        lock_version: signing.app.lock_version,
        document_hash: signing.agreement.document_hash,
        document_id: signing.document.id,
        pdf_sha256: signing.document.pdf_sha256,
        acknowledged: true,
        confirm_simulation: true,
      });
      if (!mounted.current || run.current !== token) {
        void api
          .cancelSignature(signing.agreement.id, attempt.id)
          .catch(() => undefined);
        return;
      }
      pendingAttempt.current = {
        agreement: signing.agreement.id,
        attempt: attempt.id,
      };
      setSigning({ ...signing, attempt });
      setStage("code");
    } catch (cause) {
      if (mounted.current) setError(cause);
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function confirmed() {
    if (!mounted.current) return;
    pendingAttempt.current = null;
    setSignatureConfirmed(true);
    setStage("closed");
    setSuccess(true);
    setError(null);
    const fresh = await reload();
    if (!mounted.current) return;
    await refresh();
    if (!mounted.current) return;
    const agreement = fresh && currentOffer(fresh)?.agreement;
    if (fresh && agreement) {
      // A copy failure is represented by the persistent document panel, never a second sign.
      try {
        await api.generateDocument(
          agreement.id,
          {
            lock_version: fresh.lock_version,
            document_hash: agreement.document_hash,
          },
          true,
        );
        await reload();
      } catch {
        /* Signed stays signed; panel exposes explicit copy retry. */
      }
    }
  }
  async function verifyStatus() {
    if (!signing) return;
    try {
      const result = await api.agreement(signing.agreement.id);
      if (result.signed_at) {
        await confirmed();
        return;
      }
      await reload();
      if (mounted.current)
        setError(
          new Error(
            "Сервер пока не подтвердил подпись. Она не повторялась автоматически. Проверьте состояние или закройте окно.",
          ),
        );
    } catch (cause) {
      if (mounted.current) setError(cause);
    }
  }
  async function submit(value: Signing) {
    if (!value.attempt || inFlight.current || !mounted.current) return;
    inFlight.current = true;
    setStage("sending");
    setCode(value.attempt.demo_code);
    try {
      const signed = await api.sign(value.agreement.id, {
        lock_version: value.app.lock_version,
        document_hash: value.agreement.document_hash,
        document_id: value.document.id,
        pdf_sha256: value.document.pdf_sha256,
        attempt_id: value.attempt.id,
        code: value.attempt.demo_code,
        confirm_simulation: true,
      });
      if (!signed.signed_at) throw new Error("Сервер не подтвердил подпись");
      await confirmed();
    } catch (cause) {
      if (!mounted.current) return;
      // Only a read after an uncertain response, never an automatic second POST.
      try {
        const server = await api.agreement(value.agreement.id);
        if (server.signed_at) {
          await confirmed();
          return;
        }
      } catch {
        /* Keep the unknown outcome visible. */
      }
      await reload();
      if (mounted.current) {
        setStage("error");
        setError(cause);
      }
    } finally {
      inFlight.current = false;
    }
  }
  useEffect(() => {
    if (stage !== "code" || !signing?.attempt) return;
    const token = run.current;
    timer.current = setTimeout(() => {
      if (mounted.current && token === run.current)
        void submit(signing).catch((cause: unknown) => {
          // A navigation may abort a follow-up card read as well as the POST.
          // Never leave that async branch unhandled or start another signature.
          if (mounted.current) {
            setStage("error");
            setError(cause);
          }
        });
    }, 1000);
    return () => clearTimeout(timer.current);
    // One timer per server attempt; StrictMode cleanup cancels the first setup.
  }, [stage, signing]);
  function close() {
    if (inFlight.current || stage === "sending") return;
    clearTimeout(timer.current);
    run.current++;
    const pending = pendingAttempt.current;
    pendingAttempt.current = null;
    if (pending)
      cancelling.current = api
        .cancelSignature(pending.agreement, pending.attempt)
        .catch(() => undefined);
    setStage("closed");
    setCode("");
    setAcknowledged(false);
    setSigning(null);
    setError(null);
  }
  return (
    <>
      {app.status === "accepted" && signatureConfirmed ? (
        <Notice>
          Сервер подтвердил подпись. Карточку пока не удалось обновить.
          Повторное подписание не требуется. Обновите карточку; ожидается
          моделируемая выдача специалистом.
        </Notice>
      ) : null}
      {app.status === "accepted" && !signatureConfirmed ? (
        <Button
          ref={trigger}
          block
          size={48}
          view="accent"
          disabled={disabled || busy || stage !== "closed"}
          loading={busy}
          onClick={() => void prepare()}
        >
          Подписать договор
        </Button>
      ) : null}
      {app.status === "accepted" && !signatureConfirmed && disabled ? (
        <p>
          {reasons[actionFor(app, "sign_agreement")?.reason_code ?? ""] ??
            "Действие недоступно. Обновите карточку."}
        </p>
      ) : null}
      {error && stage === "closed" ? (
        <ErrorNotice error={error} retry={() => void reload()} />
      ) : null}
      <Dialog
        open={stage === "review"}
        title="Просмотр договора"
        onClose={close}
        busy={busy}
        returnFocusRef={trigger}
        footer={
          <>
            <Button onClick={close} disabled={busy}>
              Отмена
            </Button>
            <Button
              view="accent"
              disabled={!acknowledged || busy}
              loading={busy}
              onClick={() => void begin()}
            >
              Подписать договор
            </Button>
          </>
        }
      >
        {signing ? (
          <>
            <p>
              Договор {signing.agreement.number}. Финансовые условия и PDF этой
              версии сохраняются неизменными.
            </p>
            <PdfLinks agreement={signing.agreement} />
            <CreditCost value={signing.agreement.cost_breakdown} />
            <Checkbox
              block
              label="Я ознакомлен с условиями договора и понимаю, что подпись и выдача являются демонстрацией"
              checked={acknowledged}
              onChange={(_, { checked }) => setAcknowledged(checked)}
            />
          </>
        ) : null}
        {error ? <ErrorNotice error={error} /> : null}
      </Dialog>
      <Dialog
        open={["code", "sending", "error"].includes(stage)}
        title="Подтверждение подписания"
        onClose={close}
        busy={stage === "sending"}
        returnFocusRef={trigger}
        footer={
          stage === "error" ? (
            <>
              <Button onClick={() => void verifyStatus()}>
                Проверить состояние подписи
              </Button>
              <Button onClick={close}>Закрыть</Button>
            </>
          ) : stage === "code" ? (
            <Button onClick={close}>Отмена</Button>
          ) : undefined
        }
      >
        <p>
          Демонстрация SMS-подтверждения. Сообщение не отправляется. Код
          появится автоматически.
        </p>
        <Input
          block
          label="Шестизначный демо-код"
          labelView="outer"
          value={code}
          readOnly
          inputMode="numeric"
          maxLength={6}
        />
        <p className={s.status} aria-live="polite">
          {stage === "sending"
            ? "Демо-код получен. Подтверждаем подписание…"
            : stage === "code"
              ? "Ожидаем демонстрационный код…"
              : "Подпись не подтверждена. Автоматического повтора не будет."}
        </p>
        {stage === "sending" ? (
          <Notice>
            Запрос отправлен. Закрытие страницы не гарантирует отмену: сервер
            мог уже сохранить подпись.
          </Notice>
        ) : null}
        {error ? <ErrorNotice error={error} /> : null}
      </Dialog>
      <CompletionDialog
        open={success}
        title="Договор подписан в демо-режиме"
        onClose={() => setSuccess(false)}
        returnFocusRef={trigger}
      >
        <p>Ожидается моделируемая выдача специалистом.</p>
      </CompletionDialog>
    </>
  );
}

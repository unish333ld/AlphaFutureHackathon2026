import { useEffect, useRef, useState, type MouseEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { useAuth } from "../app/auth";
import { useRefreshCredit } from "../app/queries";
import {
  api,
  type Action,
  type ActionName,
  type Application,
} from "../shared/api/client";
import { ApiError } from "../shared/api/errors";
import { beginIntent, clearIntent, readIntent } from "../shared/api/intent";
import { CreditCost } from "./CreditDisclosure";
import {
  actionFor,
  actionLabels,
  currentOffer,
  money,
  nextSteps,
  rate,
  reasons,
} from "../entities/credit";
import {
  Button,
  Dialog,
  ErrorNotice,
  Facts,
  Notice,
  Panel,
  Textarea,
  useRetryCooldown,
} from "../shared/ui/kit";
import { LinkButton } from "../shared/ui/navigation";
import s from "../app/layout.module.css";

type Confirmation = {
  action: Action;
  version: number;
  app: Application;
};
const questionSchema = z
  .string()
  .trim()
  .min(1, "Укажите, какие сведения нужны")
  .max(1000, "Не более 1000 символов");
export function ApplicationActions({
  app,
  reload,
}: {
  app: Application;
  reload: () => Promise<Application | undefined>;
}) {
  const { user } = useAuth();
  const refresh = useRefreshCredit();
  const staff = user?.system_role === "specialist";
  const trigger = useRef<HTMLButtonElement | null>(null);
  const dispatching = useRef(false);
  const [dialog, setDialog] = useState<Confirmation | null>(null);
  const [question, setQuestion] = useState("");
  const [questionError, setQuestionError] = useState("");
  const [discardQuestion, setDiscardQuestion] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const cooldown = useRetryCooldown(error);
  const [message, setMessage] = useState("");
  const [preparing, setPreparing] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const offer = currentOffer(app);
  const agreement = offer?.agreement;
  useEffect(() => {
    if (!staff || !user || !agreement) return;
    const intent = readIntent(user.id, agreement.id);
    if (agreement.disbursement) {
      if (intent) clearIntent(user.id, agreement.id);
      setUncertain(false);
    } else if (intent) setUncertain(true);
  }, [staff, user, agreement]);
  const mutation = useMutation({
    retry: false,
    mutationFn: async (confirmation: Confirmation) => {
      setError(null);
      setMessage("");
      const action = confirmation.action;
      let key: string | undefined;
      try {
        if (action.action === "disburse") {
          if (!user || !action.target_id)
            throw new Error("Missing issue target");
          key = beginIntent(user.id, action.target_id).key;
        }
        await api.action(
          action,
          confirmation.version,
          action.action === "request_information"
            ? { question: question.trim() }
            : {},
          key,
        );
        if (action.action === "disburse" && user && action.target_id) {
          clearIntent(user.id, action.target_id);
          setUncertain(false);
        }
        setDialog(null);
        setQuestion("");
        await refresh();
        setMessage(
          action.action === "request_information"
            ? "Запрос отправлен клиенту."
            : "",
        );
      } catch (cause) {
        setError(cause);
        if (
          cause instanceof ApiError &&
          (cause.status === 409 || cause.uncertain)
        ) {
          const fresh = await reload();
          await refresh();
          if (action.action === "disburse" && user && action.target_id) {
            if (fresh && currentOffer(fresh)?.agreement?.disbursement) {
              clearIntent(user.id, action.target_id);
              setUncertain(false);
              setDialog(null);
              setError(null);
              setMessage(
                "После потери ответа сервер подтвердил моделируемую выдачу. Повторный запрос не отправлялся.",
              );
            } else setUncertain(true);
          }
        }
        throw cause;
      }
    },
  });
  const pending = mutation.isPending || preparing;
  function dispatch(confirmation: Confirmation) {
    // React can batch both click handlers before isPending reaches the button.
    if (dispatching.current) return;
    dispatching.current = true;
    mutation.mutate(confirmation, {
      onSettled: () => {
        dispatching.current = false;
      },
    });
  }
  async function open(name: ActionName) {
    if (dispatching.current || pending || cooldown) return;
    const original = actionFor(app, name);
    if (!original?.allowed || !original.target_id) return;
    setError(null);
    setMessage("");
    if (["claim", "release", "retry_checks"].includes(name)) {
      dispatch({ action: original, version: app.lock_version, app });
      return;
    }
    setPreparing(true);
    try {
      const fresh = await reload();
      if (!fresh) throw new ApiError(0, null);
      await refresh();
      const action = actionFor(fresh, name);
      if (!action?.allowed || !action.target_id)
        throw new ApiError(409, {
          detail:
            reasons[action?.reason_code ?? ""] ??
            "Действие больше недоступно. Проверьте карточку.",
        });
      setQuestionError("");
      setDiscardQuestion(false);
      setDialog({
        action,
        version: fresh.lock_version,
        app: fresh,
      });
    } catch (cause) {
      setError(cause);
    } finally {
      setPreparing(false);
    }
  }
  function close() {
    if (dispatching.current || pending) return;
    if (
      dialog?.action.action === "request_information" &&
      question.trim() &&
      !discardQuestion
    ) {
      setDiscardQuestion(true);
      return;
    }
    setDialog(null);
    setDiscardQuestion(false);
    setQuestion("");
    setQuestionError("");
  }
  function confirm() {
    if (
      !dialog ||
      pending ||
      cooldown > 0 ||
      (error instanceof ApiError && error.status === 409)
    )
      return;
    if (dialog.action.action === "request_information") {
      const parsed = questionSchema.safeParse(question);
      if (!parsed.success) {
        setQuestionError(parsed.error.issues[0]?.message ?? "Проверьте вопрос");
        return;
      }
    }
    dispatch(dialog);
  }
  const clientNames: ActionName[] =
    app.status === "draft"
      ? ["update_draft"]
      : app.status === "needs_info"
        ? ["provide_information"]
        : app.status === "offered"
          ? ["accept_offer", "decline_offer", "revise"]
          : app.status === "accepted"
            ? []
            : app.status === "review"
              ? ["revise"]
              : app.status === "checking"
                ? ["retry_checks"]
                : [];
  const bankNames: ActionName[] = [
    "issued",
    "rejected",
    "declined",
    "expired",
    "draft",
    "submitted",
  ].includes(app.status)
    ? []
    : [
        ...(!app.assigned_to || app.assigned_to.id !== user?.id
          ? ["claim" as const]
          : []),
        ...(app.status === "signed" ? ["disburse" as const] : []),
        ...([
          "review",
          "checking",
          "needs_info",
          "offered",
          "accepted",
        ].includes(app.status)
          ? ["decide" as const]
          : []),
        ...(app.status === "checking" ? ["retry_checks" as const] : []),
        ...(["review", "checking"].includes(app.status)
          ? ["request_information" as const]
          : []),
        ...(app.assigned_to?.id === user?.id ? ["release" as const] : []),
      ];
  const available = (staff ? bankNames : clientNames)
    .map((name) => actionFor(app, name))
    .filter((value): value is Action => !!value);
  const targetOffer = dialog ? currentOffer(dialog.app) : offer;
  const dialogTitle =
    dialog?.action.action === "request_information"
      ? "Проверка введённых данных"
      : dialog
        ? actionLabels[dialog.action.action]
        : "";
  return (
    <Panel title={staff ? "Действия специалиста" : "Следующий шаг"}>
      <p className={s.muted}>{nextSteps[app.status]}</p>
      {error && !dialog ? (
        <ErrorNotice
          error={error}
          retry={() => {
            void reload();
          }}
        />
      ) : null}
      {message ? <Notice tone="success">{message}</Notice> : null}
      {uncertain ? (
        <Notice tone="warning" title="Предыдущая выдача не подтверждена">
          Сначала проверяем сервер. Если выдачи нет и действие разрешено, вы
          можете осознанно повторить его с тем же ключом. Новый ключ
          автоматически не создаётся.
          <div className={s.actions}>
            <Button
              size={40}
              onClick={() => {
                void reload().then(() => refresh());
              }}
              disabled={pending}
            >
              Проверить результат выдачи
            </Button>
          </div>
        </Notice>
      ) : null}
      <div className={s.stack}>
        {available.map((action, index) => {
          const enabled = action.allowed && !!action.target_id;
          const formPath =
            action.action === "update_draft"
              ? `/app/loans/${app.id}/edit`
              : action.action === "provide_information"
                ? `/app/loans/${app.id}/edit?mode=answer`
                : action.action === "revise"
                  ? `/app/loans/${app.id}/edit?mode=revise`
                  : null;
          const descriptionId = `reason-${action.action}`;
          return (
            <div key={action.action}>
              {formPath && enabled ? (
                <LinkButton
                  to={formPath}
                  view={index === 0 ? "accent" : "secondary"}
                >
                  {actionLabels[action.action]}
                </LinkButton>
              ) : (
                <Button
                  block
                  size={48}
                  view={index === 0 && enabled ? "accent" : "secondary"}
                  disabled={!enabled || pending || cooldown > 0}
                  loading={pending && index === 0}
                  aria-describedby={!enabled ? descriptionId : undefined}
                  onClick={(event: MouseEvent<HTMLButtonElement>) => {
                    trigger.current = event.currentTarget;
                    void open(action.action);
                  }}
                >
                  {uncertain && action.action === "disburse"
                    ? "Повторить с тем же ключом"
                    : actionLabels[action.action]}
                </Button>
              )}
              {!enabled ? (
                <p id={descriptionId} className={s.muted}>
                  {reasons[action.reason_code ?? ""] ??
                    "Действие недоступно. Обновите карточку."}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
      <Dialog
        returnFocusRef={trigger}
        title={discardQuestion ? "Закрыть без отправки?" : dialogTitle}
        open={!!dialog}
        onClose={close}
        busy={pending}
        footer={
          discardQuestion ? (
            <>
              <Button onClick={() => setDiscardQuestion(false)}>
                Вернуться к вопросу
              </Button>
              <Button view="accent" onClick={close}>
                Закрыть без отправки
              </Button>
            </>
          ) : (
            <>
              <Button onClick={close} disabled={pending}>
                Отмена
              </Button>
              <Button
                view="accent"
                onClick={confirm}
                loading={mutation.isPending}
                disabled={
                  pending ||
                  cooldown > 0 ||
                  (error instanceof ApiError && error.status === 409)
                }
              >
                {dialog?.action.action === "decide"
                  ? "Запустить правила"
                  : dialog?.action.action === "request_information"
                    ? "Отправить запрос"
                    : "Подтвердить"}
              </Button>
            </>
          )
        }
      >
        {discardQuestion ? (
          <p>Текст запроса будет удалён. Клиенту ничего не отправлено.</p>
        ) : (
          <>
            {dialog?.action.action === "decide" ? (
              <>
                <p>
                  Правила рассмотрят актуальные данные и проверки. Возможны
                  одобрение, встречные условия или отказ.
                </p>
                <Notice>Итоговые условия определяются автоматически.</Notice>
              </>
            ) : null}
            {dialog?.action.action === "request_information" ? (
              <>
                <p>
                  Укажите, какие уже введённые сведения нужно проверить. После
                  ответа клиента проверки выполнятся снова.
                </p>
                <Textarea
                  id="clarification-question"
                  aria-label="Какие данные нужно проверить?"
                  aria-invalid={!!questionError}
                  label="Какие данные нужно проверить?"
                  labelView="outer"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  maxLength={1000}
                  minRows={4}
                  block
                  error={questionError}
                />
              </>
            ) : null}
            {dialog?.action.action === "accept_offer" ||
            dialog?.action.action === "decline_offer" ? (
              <>
                <p>
                  {dialog.action.action === "accept_offer"
                    ? "Вы принимаете эти условия. После этого договор будет доступен для просмотра и подтверждения."
                    : "Предложение будет отклонено, а заявка завершена. Это действие нельзя отменить в текущем процессе."}
                </p>
                {targetOffer ? (
                  <>
                    <Facts
                      rows={[
                        { label: "Сумма", value: money(targetOffer.amount) },
                        {
                          label: "Ставка",
                          value: rate(targetOffer.annual_rate),
                        },
                        {
                          label: "Срок",
                          value: `${targetOffer.term_months} мес.`,
                        },
                        {
                          label: "Платёж",
                          value: money(targetOffer.monthly_payment),
                        },
                      ]}
                    />
                    <CreditCost value={targetOffer.cost_breakdown} />
                  </>
                ) : null}
              </>
            ) : null}
            {dialog?.action.action === "disburse" ? (
              <>
                <Notice tone="warning" title="Только моделирование">
                  Реального перевода денег не будет. Одна моделируемая выдача
                  закрепляется за договором.
                </Notice>
                <Facts
                  rows={[
                    {
                      label: "Договор",
                      value:
                        currentOffer(dialog.app)?.agreement?.number ??
                        "Нет данных",
                    },
                    {
                      label: "Сумма",
                      value: money(currentOffer(dialog.app)?.amount),
                    },
                  ]}
                />
                {uncertain ? (
                  <p>
                    Повтор будет отправлен с сохранённым ключом предыдущего
                    действия.
                  </p>
                ) : null}
              </>
            ) : null}
            {error ? (
              <>
                <ErrorNotice error={error} />
                {error instanceof ApiError && error.status === 409 ? (
                  <p>
                    Ввод сохранён. Закройте диалог, проверьте обновлённую
                    карточку и выберите действие заново.
                  </p>
                ) : null}
              </>
            ) : null}
          </>
        )}
      </Dialog>
    </Panel>
  );
}

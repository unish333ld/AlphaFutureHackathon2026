import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { ButtonDesktop as Button } from "@alfalab/core-components/button/desktop";
import { MagicWandSIcon } from "@alfalab/icons-glyph/MagicWandSIcon";
import { useAuth } from "../app/auth";
import { useCatalogs } from "../app/queries";
import { displayName } from "../entities/credit";
import { api, type AssistantStep } from "../shared/api/client";
import { ApiError } from "../shared/api/errors";
import {
  Choice,
  Dialog,
  Input,
  Loading,
  Notice,
  Textarea,
} from "../shared/ui/kit";
import { AssistantFacts } from "./AssistantFacts";
import { parseAssistantDraft, type AssistantDraft } from "./assistantDraft";
import { useAssistantForm, type FormSnapshot } from "./AssistantFormContext";
import s from "./assistant.module.css";

type Preview = {
  value: AssistantDraft;
  before: FormSnapshot | null;
  stepId: string;
  version: number;
};

export default function AssistantWidget() {
  const { expired } = useAuth();
  const bridge = useAssistantForm();
  const { companies } = useCatalogs();
  const location = useLocation();
  const navigate = useNavigate();
  const routeId = /^\/app\/loans\/([0-9a-f-]{36})(?:\/|$)/i.exec(
    location.pathname,
  )?.[1];
  const [routeApplication, setRouteApplication] = useState<Awaited<
    ReturnType<typeof api.application>
  > | null>(null);
  const [routeError, setRouteError] = useState(false);
  const [companyChoice, setCompanyChoice] = useState("");
  const [open, setOpen] = useState(false);
  const [narrow, setNarrow] = useState(() => window.innerWidth < 1180);
  const [step, setStep] = useState<AssistantStep | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [openingAttempt, setOpeningAttempt] = useState(0);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const actionController = useRef<AbortController | null>(null);
  const currentStep = useRef<AssistantStep | null>(null);
  const lastDraftRequest = useRef<FormSnapshot | null>(null);
  const companyId = routeId
    ? routeApplication?.id === routeId
      ? routeApplication.company
      : ""
    : bridge.selection?.company ||
      companyChoice ||
      companies.data?.[0]?.id ||
      "";
  const applicationId =
    routeId && routeApplication?.id === routeId ? routeId : undefined;
  const companyName =
    displayName(
      companies.data?.find((value) => value.id === companyId)?.name,
    ) || "Компания";

  const acceptState = useCallback(
    (incoming: AssistantStep, preserveInput = false) => {
      const previous = currentStep.current;
      if (
        previous &&
        previous.conversation_id === incoming.conversation_id &&
        incoming.version < previous.version
      )
        return;
      currentStep.current = incoming;
      setStep(incoming);
      if (previous?.step_id !== incoming.step_id && !preserveInput) {
        setDraft(incoming.input?.value ?? incoming.saved_input ?? "");
      }
    },
    [],
  );

  useEffect(() => {
    const resize = () => setNarrow(window.innerWidth < 1180);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    if (!open || !routeId) {
      setRouteApplication(null);
      setRouteError(false);
      return;
    }
    const controller = new AbortController();
    setRouteError(false);
    void api
      .application(routeId, false, controller.signal)
      .then(setRouteApplication)
      .catch(() => {
        if (!controller.signal.aborted) setRouteError(true);
      });
    return () => controller.abort();
  }, [open, routeId]);

  useEffect(() => {
    panel.current?.toggleAttribute("inert", !open);
    if (!open) return;
    document.body.dataset.assistantOpen = "true";
    const root = document.getElementById("root");
    if (root && narrow) root.inert = true;
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      delete document.body.dataset.assistantOpen;
      if (root) root.inert = false;
    };
  }, [open, narrow]);

  useEffect(() => {
    if (!open || !companyId || expired || (routeId && !applicationId)) return;
    const token = ++generation.current;
    const controller = new AbortController();
    actionController.current?.abort();
    actionController.current = null;
    inFlight.current = false;
    setBusy(false);
    setPreview(null);
    setLoading(true);
    setError("");
    setStep(null);
    currentStep.current = null;
    void api
      .assistantCurrent(companyId, applicationId, controller.signal)
      .then((value) => {
        if (token === generation.current) acceptState(value);
      })
      .catch((cause) => {
        if (token === generation.current && !controller.signal.aborted)
          setError(
            cause instanceof ApiError && !cause.uncertain
              ? cause.message
              : "Помощник сейчас недоступен. Попробуйте подключиться снова или продолжите заявку самостоятельно.",
          );
      })
      .finally(() => {
        if (token === generation.current) setLoading(false);
      });
    return () => {
      controller.abort();
      actionController.current?.abort();
      actionController.current = null;
      inFlight.current = false;
      generation.current++;
    };
  }, [
    open,
    companyId,
    applicationId,
    routeId,
    expired,
    acceptState,
    openingAttempt,
  ]);

  useEffect(() => {
    if (!open || step?.mode !== "waiting") return;
    const controller = new AbortController();
    const token = generation.current;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const fresh = await api.assistantStep(
          step.conversation_id,
          controller.signal,
        );
        if (token !== generation.current || controller.signal.aborted) return;
        acceptState(fresh, true);
        if (fresh.mode === "waiting")
          timer = window.setTimeout(() => void poll(), 1500);
      } catch {
        if (!controller.signal.aborted && token === generation.current)
          timer = window.setTimeout(() => void poll(), 3000);
      }
    };
    timer = window.setTimeout(() => void poll(), 1200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [open, step?.mode, step?.conversation_id, acceptState]);

  function close() {
    generation.current++;
    actionController.current?.abort();
    actionController.current = null;
    inFlight.current = false;
    setBusy(false);
    setOpen(false);
    setPreview(null);
    requestAnimationFrame(() =>
      trigger.current?.focus({ preventScroll: true }),
    );
  }

  useEffect(() => {
    if (!open) return;
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !preview) {
        event.preventDefault();
        close();
      }
      if (narrow && event.key === "Tab" && !preview) {
        const elements = Array.from(
          panel.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]",
          ) ?? [],
        ).filter((node) => node.getClientRects().length > 0);
        const first = elements[0],
          last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [open, narrow, preview]);

  async function reconcile(conversationId: string, token = generation.current) {
    try {
      const fresh = await api.assistantStep(conversationId);
      if (token === generation.current) {
        acceptState(fresh, true);
        setError("");
      }
      return fresh;
    } catch {
      if (token === generation.current)
        setError(
          "Не удалось проверить ответ. Ввод сохранён. Проверьте состояние позже.",
        );
      return null;
    }
  }

  async function act(value: { action_id: string } | { text: string }) {
    const selected = currentStep.current;
    if (!selected || inFlight.current || selected.mode === "waiting" || expired)
      return;
    if ("text" in value && selected.mode !== "input") return;
    if (
      "action_id" in value &&
      !selected.choices.some((choice) => choice.id === value.action_id)
    )
      return;
    const token = generation.current;
    const before = bridge.form.current?.snapshot() ?? null;
    const controller = new AbortController();
    actionController.current = controller;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await api.assistantAct(
        selected.conversation_id,
        {
          expected_version: selected.version,
          step_id: selected.step_id,
          request_id: crypto.randomUUID(),
          ...value,
        },
        controller.signal,
      );
      if (token !== generation.current) return;
      if (
        result.message?.suggested_draft &&
        Object.keys(result.message.suggested_draft).length
      )
        lastDraftRequest.current = before;
      acceptState(result);
      if (
        "action_id" in value &&
        value.action_id === "apply_draft" &&
        result.draft_ready
      )
        await reviewDraft(result, before);
    } catch (cause) {
      if (token !== generation.current || controller.signal.aborted) return;
      if (
        cause instanceof ApiError &&
        (cause.status === 409 || cause.uncertain)
      ) {
        const fresh = await reconcile(selected.conversation_id, token);
        if (fresh?.mode === "waiting") return;
        if (fresh && fresh.version > selected.version) return;
      }
      setError(
        cause instanceof ApiError
          ? (cause.normalized.fields.text ?? cause.message)
          : "Не удалось отправить ответ. Ввод сохранён.",
      );
    } finally {
      if (token === generation.current) {
        inFlight.current = false;
        setBusy(false);
      }
      if (actionController.current === controller)
        actionController.current = null;
    }
  }

  async function reviewDraft(
    state: AssistantStep,
    before: FormSnapshot | null = lastDraftRequest.current,
  ) {
    const value = parseAssistantDraft(
      state.message?.suggested_draft,
      companyId,
    );
    if (!value) {
      setError("Параметры изменились. Подготовьте предложение заново.");
      return;
    }
    const token = generation.current;
    setPreviewBusy(true);
    try {
      const fresh = await api.assistantStep(state.conversation_id);
      if (fresh.step_id !== state.step_id || !fresh.draft_ready)
        throw new Error("Параметры изменились. Проверьте актуальный шаг.");
      const product = (await api.products()).find(
        (item) => item.id === value.product,
      );
      if (
        !product ||
        Number(value.amount) < Number(product.min_amount) ||
        Number(value.amount) > Number(product.max_amount) ||
        value.term_months < product.min_term_months ||
        value.term_months > product.max_term_months
      )
        throw new Error(
          "Условия продукта изменились. Подготовьте предложение заново.",
        );
      if (
        state.message?.application_id &&
        state.message.application_version != null
      ) {
        const app = await api.application(state.message.application_id);
        if (app.lock_version !== state.message.application_version)
          throw new Error("Заявка изменилась. Проверьте её перед переносом.");
      }
      if (
        before &&
        bridge.form.current?.snapshot().fingerprint !== before.fingerprint
      )
        throw new Error(
          "Форма изменилась. Ввод сохранён; проверьте поля вручную.",
        );
      if (!before && bridge.form.current)
        throw new Error("В форме уже есть данные. Проверьте их вручную.");
      if (token === generation.current)
        setPreview({
          value,
          before,
          stepId: state.step_id,
          version: state.version,
        });
    } catch (cause) {
      if (token === generation.current)
        setError(
          cause instanceof Error
            ? cause.message
            : "Не удалось проверить параметры.",
        );
    } finally {
      if (token === generation.current) setPreviewBusy(false);
    }
  }

  async function applyDraft() {
    if (!preview || previewBusy || !step) return;
    const token = generation.current;
    setPreviewBusy(true);
    try {
      const fresh = await api.assistantStep(step.conversation_id);
      if (
        fresh.step_id !== preview.stepId ||
        fresh.version !== preview.version ||
        !fresh.draft_ready
      )
        throw new Error("Шаг изменился. Проверьте параметры ещё раз.");
      if (preview.before) {
        if (
          !bridge.form.current?.apply(preview.value, preview.before.fingerprint)
        )
          throw new Error(
            "Форма изменилась. Ввод сохранён; проверьте поля вручную.",
          );
      } else {
        if (bridge.form.current)
          throw new Error("Открыта форма с данными. Проверьте их вручную.");
        bridge.transfer.current = preview.value;
        navigate("/app/loans/new");
      }
      if (token === generation.current) {
        setPreview(null);
        close();
      }
    } catch (cause) {
      if (token === generation.current)
        setError(
          cause instanceof Error
            ? cause.message
            : "Не удалось перенести параметры.",
        );
    } finally {
      if (token === generation.current) setPreviewBusy(false);
    }
  }

  return createPortal(
    <>
      <div className={s.launcher} hidden={open && narrow}>
        <Button
          ref={trigger}
          size={40}
          view="accent"
          aria-label="Помощник по кредиту"
          aria-expanded={open}
          aria-controls="credit-assistant-panel"
          onClick={() => (open ? close() : setOpen(true))}
        >
          <MagicWandSIcon aria-hidden="true" />
          <span className={s.launcherText}>Помощник по кредиту</span>
        </Button>
      </div>
      <section
        id="credit-assistant-panel"
        ref={panel}
        className={`${s.window} ${open ? s.windowOpen : ""}`}
        role="dialog"
        aria-modal={open && narrow}
        aria-hidden={!open}
        aria-label="Помощник по кредиту"
      >
        <header className={s.header}>
          <div>
            <h2>Помощник по кредиту</h2>
            <span>Поможет с продуктом, расчётом и заявкой</span>
          </div>
          <Button
            size={32}
            view="text"
            onClick={close}
            aria-label="Закрыть помощника"
          >
            Закрыть
          </Button>
        </header>
        <div className={s.context}>
          <strong>{companyName}</strong>
          {!routeId &&
          !bridge.selection &&
          (companies.data?.length ?? 0) > 1 ? (
            <Choice
              label="Компания"
              value={companyId}
              onChange={setCompanyChoice}
              options={(companies.data ?? []).map((item) => ({
                key: item.id,
                content: displayName(item.name),
              }))}
            />
          ) : null}
        </div>
        <div className={s.stepContent} key={step?.step_id ?? "loading"}>
          {routeError ? (
            <Notice tone="error">
              Заявка недоступна. Вернитесь к списку заявок.
            </Notice>
          ) : null}
          {loading || (!step && !error && !routeError) ? (
            <Loading label="Открываем помощника…" />
          ) : null}
          {step ? (
            <>
              <div className={s.stepHeading}>
                <h3>{step.title}</h3>
                {step.prompt && step.mode !== "error" ? (
                  <p>{step.prompt}</p>
                ) : null}
              </div>
              {step.mode === "waiting" ? (
                <p role="status" aria-live="polite">
                  Готовим ответ…
                </p>
              ) : null}
              {step.mode === "result" && step.message ? (
                <article className={s.assistantMessage}>
                  <p>{step.message.content}</p>
                  <AssistantFacts
                    facts={step.message.facts}
                    suggestedDraft={step.message.suggested_draft}
                    company={step.company}
                  />
                </article>
              ) : null}
              {step.mode === "error" ? (
                <Notice tone="error">{step.prompt}</Notice>
              ) : null}
              {step.mode === "choice" ||
              step.mode === "result" ||
              step.mode === "error" ? (
                <div className={s.prompts} aria-label="Доступные варианты">
                  {step.choices.map((choice) => (
                    <button
                      type="button"
                      key={choice.id}
                      disabled={busy || previewBusy}
                      onClick={() => void act({ action_id: choice.id })}
                    >
                      {choice.label}
                    </button>
                  ))}
                  {step.draft_ready &&
                  step.message?.suggested_draft &&
                  Object.keys(step.message.suggested_draft).length ? (
                    <button
                      type="button"
                      disabled={busy || previewBusy}
                      onClick={() => void reviewDraft(step)}
                    >
                      Проверить параметры заявки
                    </button>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : null}
          {error ? (
            <Notice tone="error">
              {error}
              {step ? (
                <button
                  type="button"
                  onClick={() => void reconcile(step.conversation_id)}
                >
                  Проверить состояние
                </button>
              ) : (
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => setOpeningAttempt((value) => value + 1)}
                >
                  Попробовать подключиться снова
                </button>
              )}
            </Notice>
          ) : null}
        </div>
        {step?.mode === "input" && step.input ? (
          <div className={s.composer}>
            {step.input.kind === "text" ? (
              <Textarea
                label={step.input.label}
                aria-label={step.input.label}
                labelView="outer"
                block
                value={draft}
                onChange={(_, { value }) => setDraft(value)}
                maxLength={step.input.max_length}
                disabled={busy}
                hint={step.input.hint}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    if (draft.trim()) void act({ text: draft.trim() });
                  }
                }}
              />
            ) : (
              <Input
                label={step.input.label}
                aria-label={step.input.label}
                labelView="outer"
                block
                type="text"
                inputMode={step.input.kind === "money" ? "decimal" : "numeric"}
                value={draft}
                maxLength={step.input.max_length}
                disabled={busy}
                onChange={(_, { value }) => setDraft(value)}
                hint={step.input.hint}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && draft.trim())
                    void act({ text: draft.trim() });
                }}
              />
            )}
            <div className={s.sendRow}>
              <Button
                size={40}
                view="accent"
                disabled={!draft.trim() || busy || previewBusy}
                onClick={() => void act({ text: draft.trim() })}
              >
                Продолжить
              </Button>
            </div>
          </div>
        ) : null}
      </section>
      <Dialog
        title="Проверить предложенные параметры"
        open={!!preview}
        onClose={() => setPreview(null)}
        busy={previewBusy}
        footer={
          <>
            <Button disabled={previewBusy} onClick={() => setPreview(null)}>
              Отмена
            </Button>
            <Button
              view="accent"
              disabled={previewBusy}
              onClick={() => void applyDraft()}
            >
              Перенести в форму
            </Button>
          </>
        }
      >
        {preview ? (
          <>
            <p>
              Изменения появятся только в форме. Сохранение и отправку выполните
              отдельно.
            </p>
            <dl>
              {(["amount", "term_months", "purpose"] as const).map((key) => (
                <div key={key}>
                  <dt>
                    {
                      {
                        amount: "Сумма, ₽",
                        term_months: "Срок, месяцев",
                        purpose: "Цель",
                      }[key]
                    }
                  </dt>
                  <dd>
                    {String(preview.before?.[key] || "Не задано")} →{" "}
                    {preview.value[key]}
                  </dd>
                </div>
              ))}
            </dl>
          </>
        ) : null}
      </Dialog>
    </>,
    document.body,
  );
}

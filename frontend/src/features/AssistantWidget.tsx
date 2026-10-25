import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth";
import { useCatalogs } from "../app/queries";
import {
  api,
  type AssistantConversation,
  type AssistantMessage,
} from "../shared/api/client";
import { ApiError } from "../shared/api/errors";
import {
  Button,
  Choice,
  Dialog,
  Loading,
  Notice,
  Textarea,
} from "../shared/ui/kit";
import { AssistantFacts } from "./AssistantFacts";
import { parseAssistantDraft, type AssistantDraft } from "./assistantDraft";
import { useAssistantForm, type FormSnapshot } from "./AssistantFormContext";
import s from "./assistant.module.css";

const shortDate = (value: string) =>
  new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
type Preview = { value: AssistantDraft; before: FormSnapshot | null };
export default function AssistantWidget() {
  const { user, expired } = useAuth();
  const userId = user!.id;
  const bridge = useAssistantForm();
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const { companies, products } = useCatalogs();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const messagesNode = useRef<HTMLDivElement>(null);
  const generation = useRef(0);
  const loadId = useRef(0);
  const sending = useRef(false);
  const scrollToBottom = useRef(true);
  const scrollAnchor = useRef<{ height: number; top: number } | null>(null);
  const snapshots = useRef(new Map<string, FormSnapshot | null>());
  const [open, setOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [companyChoice, setCompanyChoice] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [oldestPage, setOldestPage] = useState(1);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [retryAt, setRetryAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [narrow, setNarrow] = useState(() => window.innerWidth < 1180);
  const routeId = /^\/app\/loans\/([0-9a-f-]{36})(?:\/|$)/i.exec(
    location.pathname,
  )?.[1];
  const routeApplication = useQuery({
    queryKey: ["user", userId, "assistant", "route-application", routeId],
    queryFn: ({ signal }) => api.application(routeId!, false, signal),
    enabled: open && !!routeId,
  });
  const history = useQuery({
    queryKey: ["user", userId, "assistant", "conversations", historyPage],
    queryFn: ({ signal }) => api.assistantConversations(historyPage, signal),
    enabled: open && historyOpen,
  });
  const selected = useQuery({
    queryKey: ["user", userId, "assistant", "conversation", selectedId],
    queryFn: ({ signal }) => api.assistantConversation(selectedId!, signal),
    enabled: open && !!selectedId,
    refetchOnWindowFocus: false,
  });
  const conversation = selected.data;
  const companyId =
    conversation?.company ||
    routeApplication.data?.company ||
    bridge.selection?.company ||
    companyChoice ||
    companies.data?.[0]?.id ||
    "";
  const applicationContext = selectedId
    ? (conversation?.application ?? undefined)
    : routeApplication.data?.id;
  const applicationNumber = selectedId
    ? conversation?.application_number
    : routeApplication.data?.number;
  const companyName =
    companies.data?.find((item) => item.id === companyId)?.name ?? "Компания";
  const chatKey = selectedId ?? `new:${companyId}:${routeId ?? ""}`;
  const draft = inputs[chatKey] ?? "";
  const wait = Math.max(0, Math.ceil((retryAt - now) / 1000));
  const contextReady =
    !!companyId &&
    (!routeId ||
      (routeApplication.isSuccess && !routeApplication.isFetching)) &&
    (!selectedId || selected.isSuccess) &&
    !expired;
  const mismatch =
    !!selectedId &&
    ((conversation?.application ?? undefined) !== routeId ||
      (!!bridge.selection &&
        conversation?.company !== bridge.selection.company));
  const prompts = applicationContext
    ? [
        "Какой сейчас статус и что мне делать дальше?",
        "Объясни сохранённое решение и предложение",
        "Что нужно ответить банку?",
      ]
    : [
        "Какие кредитные продукты доступны?",
        "Какие данные нужны для заявки?",
        "Как рассчитать предварительный платёж?",
      ];
  const setDraft = (value: string) =>
    setInputs((current) => ({ ...current, [chatKey]: value }));
  function resetChat(id: string | null = null) {
    generation.current++;
    loadId.current++;
    sending.current = false;
    setBusy(false);
    setLoadingMessages(false);
    setSelectedId(id);
    setMessages([]);
    setError("");
    setAnnouncement("");
    setHistoryError(false);
    setHistoryOpen(false);
    setPreview(null);
    scrollToBottom.current = true;
  }
  useEffect(() => {
    resetChat();
  }, [location.pathname, bridge.selection?.company, bridge.selection?.product]);
  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < 1180);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  useEffect(() => {
    if (!open) return;
    document.body.dataset.assistantOpen = "true";
    const root = document.getElementById("root");
    if (root && narrow) root.inert = true;
    return () => {
      delete document.body.dataset.assistantOpen;
      if (root) root.inert = false;
    };
  }, [open, narrow]);
  useEffect(() => {
    if (!retryAt) return;
    const timer = window.setInterval(() => {
      const timestamp = Date.now();
      setNow(timestamp);
      if (timestamp >= retryAt) setRetryAt(0);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [retryAt]);
  function close() {
    setOpen(false);
    setPreview(null);
    requestAnimationFrame(() =>
      trigger.current?.focus({ preventScroll: true }),
    );
  }
  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented && !preview) {
        event.preventDefault();
        close();
      }
      if (narrow && event.key === "Tab" && !preview) {
        const focusable = Array.from(
          panel.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex='0']",
          ) ?? [],
        ).filter((item) => item.getClientRects().length > 0);
        const first = focusable[0],
          last = focusable[focusable.length - 1];
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
  const loadMessages = useCallback(async (id: string) => {
    const token = ++loadId.current;
    setLoadingMessages(true);
    setHistoryError(false);
    try {
      const first = await api.assistantMessages(id);
      const lastPage = Math.max(1, Math.ceil(first.count / 25));
      const last =
        lastPage === 1 ? first : await api.assistantMessages(id, lastPage);
      if (token !== loadId.current) return null;
      scrollToBottom.current = true;
      setMessages(last.results);
      setOldestPage(lastPage);
      return last.results;
    } catch {
      if (token === loadId.current) setHistoryError(true);
      return null;
    } finally {
      if (token === loadId.current) setLoadingMessages(false);
    }
  }, []);
  useEffect(() => {
    if (open && selectedId) void loadMessages(selectedId);
    return () => {
      loadId.current++;
    };
  }, [open, selectedId, loadMessages]);
  useLayoutEffect(() => {
    const node = messagesNode.current;
    if (!node) return;
    if (scrollAnchor.current) {
      node.scrollTop =
        scrollAnchor.current.top +
        node.scrollHeight -
        scrollAnchor.current.height;
      scrollAnchor.current = null;
    } else if (scrollToBottom.current) {
      node.scrollTop = node.scrollHeight;
      scrollToBottom.current = false;
    }
  }, [messages]);
  async function loadOlder() {
    if (!selectedId || oldestPage <= 1 || loadingMessages) return;
    const token = loadId.current;
    setLoadingMessages(true);
    try {
      const previous = await api.assistantMessages(selectedId, oldestPage - 1);
      if (token !== loadId.current) return;
      const node = messagesNode.current;
      if (node)
        scrollAnchor.current = {
          height: node.scrollHeight,
          top: node.scrollTop,
        };
      setMessages((current) => [...previous.results, ...current]);
      setOldestPage((page) => page - 1);
    } catch {
      if (token === loadId.current) setHistoryError(true);
    } finally {
      if (token === loadId.current) setLoadingMessages(false);
    }
  }
  async function send(prompt = draft) {
    const text = prompt.trim();
    if (!text || text.length > 2000 || !contextReady || sending.current || wait)
      return;
    const epoch = generation.current;
    const before = bridge.form.current?.snapshot() ?? null;
    sending.current = true;
    setBusy(true);
    setError("");
    setAnnouncement("");
    let current: AssistantConversation | undefined = conversation;
    let targetKey = chatKey;
    try {
      if (!selectedId) {
        current = await api.assistantCreateConversation(
          companyId,
          applicationContext,
        );
        if (epoch !== generation.current) return;
        targetKey = current.id;
        setInputs((all) => ({ ...all, [targetKey]: text, [chatKey]: "" }));
        client.setQueryData(
          ["user", userId, "assistant", "conversation", current.id],
          current,
        );
        setSelectedId(current.id);
      }
      if (!current) throw new Error("Диалог ещё загружается.");
      const reply = await api.assistantSend(current.id, text, current.version);
      if (epoch !== generation.current) return;
      snapshots.current.set(reply.message.id, before);
      client.setQueryData(
        ["user", userId, "assistant", "conversation", current.id],
        { ...current, version: reply.version },
      );
      setInputs((all) => ({ ...all, [targetKey]: "" }));
      await loadMessages(current.id);
      await client.invalidateQueries({
        queryKey: ["user", userId, "assistant", "conversations"],
      });
      setAnnouncement(
        reply.model_status === "degraded"
          ? "Модель не завершила объяснение. Показаны только проверенные серверные данные."
          : "Ответ получен.",
      );
    } catch (cause) {
      if (epoch !== generation.current) return;
      if (cause instanceof ApiError && cause.status === 429) {
        setRetryAt(Date.now() + Math.max(1, cause.retryAfter) * 1000);
        setNow(Date.now());
        setError(
          "Лимит запросов помощнику. Подождите перед повторной отправкой.",
        );
      } else if (
        cause instanceof ApiError &&
        [0, 409, 503].includes(cause.status)
      ) {
        setError(
          cause.status === 409
            ? "Заявка или диалог изменились. Ввод сохранён; проверьте обновлённые данные перед повтором."
            : "Помощник сейчас недоступен. Заявку можно продолжить без него.",
        );
        if (current) {
          const fresh = await api
            .assistantConversation(current.id)
            .catch(() => null);
          const rows = await loadMessages(current.id);
          if (epoch !== generation.current) return;
          if (fresh)
            client.setQueryData(
              ["user", userId, "assistant", "conversation", current.id],
              fresh,
            );
          if (
            fresh &&
            rows &&
            fresh.version === current.version + 1 &&
            rows.at(-2)?.role === "user" &&
            rows.at(-2)?.content === text &&
            rows.at(-1)?.role === "assistant"
          ) {
            setError("");
            setAnnouncement(
              "Ответ найден в истории. Повторная отправка не требуется.",
            );
            setInputs((all) => ({ ...all, [targetKey]: "" }));
          } else
            setAnnouncement(
              rows && fresh && fresh.version === current.version
                ? "Отправленное сообщение не найдено в истории. Ввод сохранён; повтор возможен только вручную."
                : "Исход запроса не подтверждён. Проверьте историю перед повтором.",
            );
        }
        await client.invalidateQueries({ queryKey: ["user", userId] });
      } else
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Не удалось открыть диалог. Ввод сохранён.",
        );
    } finally {
      if (epoch === generation.current) {
        sending.current = false;
        setBusy(false);
      }
    }
  }
  async function reviewDraft(value: AssistantDraft, message: AssistantMessage) {
    const epoch = generation.current;
    setError("");
    const current = bridge.form.current;
    const before = snapshots.current.get(message.id) ?? null;
    if (
      current &&
      (!before || current.snapshot().fingerprint !== before.fingerprint)
    ) {
      setError(
        "Форма изменилась после вопроса. Запросите новое предложение; ваш ввод сохранён.",
      );
      return;
    }
    if (
      current &&
      (value.company !== before?.company || value.product !== before?.product)
    ) {
      setError(
        "В открытой форме выбраны другая компания или продукт. Выберите их явно в форме и запросите новое предложение.",
      );
      return;
    }
    try {
      const catalog = await api.products();
      const product = catalog.find((item) => item.id === value.product);
      if (
        !product ||
        Number(value.amount) < Number(product.min_amount) ||
        Number(value.amount) > Number(product.max_amount) ||
        value.term_months < product.min_term_months ||
        value.term_months > product.max_term_months
      )
        throw new Error(
          "Продукт или ограничения изменились. Запросите новое предложение.",
        );
      if (
        message.application_id &&
        message.application_version !== null &&
        message.application_version !== undefined
      ) {
        const app = await api.application(message.application_id);
        if (app.lock_version !== message.application_version)
          throw new Error(
            "Заявка изменилась после ответа. Обновите карточку и запросите новое предложение.",
          );
      }
      if (epoch === generation.current) setPreview({ value, before });
    } catch (cause) {
      if (epoch === generation.current)
        setError(
          cause instanceof Error
            ? cause.message
            : "Не удалось проверить предложение.",
        );
    }
  }
  function applyDraft() {
    if (!preview || !parseAssistantDraft(preview.value, companyId)) return;
    if (preview.before) {
      if (
        !bridge.form.current?.apply(preview.value, preview.before.fingerprint)
      ) {
        setPreview(null);
        setError(
          "Форма изменилась. Предложение не применено; ваш ввод сохранён.",
        );
        return;
      }
      setPreview(null);
      close();
    } else {
      if (bridge.form.current) {
        setPreview(null);
        setError("Открыта новая форма. Запросите актуальное предложение.");
        return;
      }
      bridge.transfer.current = preview.value;
      setPreview(null);
      close();
      navigate("/app/loans/new");
    }
  }
  async function deleteChat() {
    if (
      !selectedId ||
      busy ||
      !window.confirm("Удалить этот диалог и все его сообщения?")
    )
      return;
    try {
      await api.assistantDeleteConversation(selectedId);
      resetChat();
      await client.invalidateQueries({
        queryKey: ["user", userId, "assistant"],
      });
    } catch {
      setError("Не удалось удалить диалог. Попробуйте позже.");
    }
  }
  const widget = (
    <>
      <div className={s.launcher} hidden={open && narrow}>
        <Button
          ref={trigger}
          size={40}
          view="accent"
          aria-expanded={open}
          aria-controls="saveliy-panel"
          onClick={() => (open ? close() : setOpen(true))}
        >
          Савелий
        </Button>
      </div>
      {open ? (
        <section
          id="saveliy-panel"
          ref={panel}
          className={s.window}
          role="dialog"
          aria-modal={narrow}
          aria-label="Савелий, помощник по кредиту"
        >
          <header className={s.header}>
            <div>
              <h2>
                {applicationNumber
                  ? `Помощь по заявке № ${applicationNumber}`
                  : "Помощь по продуктам"}
              </h2>
              <span>Савелий · ИИ-помощник, демо</span>
            </div>
            <Button
              size={32}
              view="text"
              aria-label="Закрыть Савелия"
              onClick={close}
            >
              Закрыть
            </Button>
          </header>
          <div className={s.context}>
            <strong>{companyName}</strong>
            {mismatch ? (
              <Notice>
                Открыт диалог{" "}
                {conversation?.application_number
                  ? `по заявке № ${conversation.application_number}`
                  : "без заявки"}
                , отличный от текущего экрана.{" "}
                <button onClick={() => resetChat()}>
                  Вернуться к текущему контексту
                </button>
              </Notice>
            ) : null}
            {!selectedId && !routeId && !bridge.selection ? (
              <Choice
                label="Компания для нового чата"
                value={companyId}
                onChange={(value) => {
                  resetChat();
                  setCompanyChoice(value);
                }}
                options={(companies.data ?? []).map((item) => ({
                  key: item.id,
                  content: item.name,
                }))}
              />
            ) : null}
            {routeApplication.isError || selected.isError ? (
              <Notice tone="error">
                Контекст недоступен. Обновите страницу или выберите доступный
                диалог.
              </Notice>
            ) : null}
            <div className={s.toolbar}>
              <Button
                size={32}
                view="text"
                onClick={() => setHistoryOpen((value) => !value)}
                aria-expanded={historyOpen}
              >
                {historyOpen ? "К диалогу" : "История"}
              </Button>
              <Button
                size={32}
                view="text"
                disabled={busy}
                onClick={() => resetChat()}
              >
                Новый чат
              </Button>
              {selectedId ? (
                <Button
                  size={32}
                  view="text"
                  disabled={busy}
                  onClick={() => void deleteChat()}
                >
                  Удалить диалог
                </Button>
              ) : null}
            </div>
          </div>
          {historyOpen ? (
            <aside className={s.historyList} aria-label="История диалогов">
              <p className={s.hint}>
                История хранится ограниченное время. Срок указан в документации
                помощника.
              </p>
              {history.isPending ? (
                <Loading label="Загружаем диалоги…" />
              ) : null}
              {history.isError ? (
                <Notice tone="error">
                  История недоступна.{" "}
                  <button onClick={() => void history.refetch()}>
                    Повторить
                  </button>
                </Notice>
              ) : null}
              {history.data?.results.length === 0 ? (
                <p>Диалогов пока нет.</p>
              ) : null}
              {history.data?.results.map((item) => (
                <button
                  key={item.id}
                  className={s.historyItem}
                  onClick={() => resetChat(item.id)}
                  disabled={busy}
                >
                  <strong>
                    {item.application_number
                      ? `Заявка № ${item.application_number}`
                      : "Общий диалог"}
                  </strong>
                  <span>
                    {companies.data?.find(
                      (company) => company.id === item.company,
                    )?.name ?? "Компания"}
                  </span>
                  <small>{shortDate(item.updated_at)}</small>
                </button>
              ))}
              {history.data && (history.data.previous || history.data.next) ? (
                <div className={s.pageButtons}>
                  <Button
                    size={32}
                    disabled={!history.data.previous}
                    onClick={() => setHistoryPage((page) => page - 1)}
                  >
                    Назад
                  </Button>
                  <span>{historyPage}</span>
                  <Button
                    size={32}
                    disabled={!history.data.next}
                    onClick={() => setHistoryPage((page) => page + 1)}
                  >
                    Далее
                  </Button>
                </div>
              ) : null}
            </aside>
          ) : (
            <>
              <div
                ref={messagesNode}
                className={s.messages}
                aria-label="Сообщения диалога"
                aria-busy={busy || loadingMessages}
              >
                {loadingMessages ? (
                  <Loading label="Загружаем сообщения…" />
                ) : null}
                {historyError ? (
                  <Notice tone="error">
                    История не загрузилась.{" "}
                    <button
                      onClick={() =>
                        selectedId && void loadMessages(selectedId)
                      }
                    >
                      Обновить историю
                    </button>
                  </Notice>
                ) : null}
                {oldestPage > 1 ? (
                  <Button
                    size={32}
                    disabled={loadingMessages}
                    onClick={() => void loadOlder()}
                  >
                    Ранние сообщения
                  </Button>
                ) : null}
                {!messages.length && !loadingMessages ? (
                  <p>
                    Помогу разобраться с условиями, статусом и следующим шагом.
                    Не вводите реальные персональные и банковские данные.
                  </p>
                ) : null}
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={
                      message.role === "user"
                        ? s.userMessage
                        : s.assistantMessage
                    }
                  >
                    <strong>
                      {message.role === "user" ? "Вы" : "Савелий"}
                    </strong>
                    {message.role === "assistant" ? (
                      <AssistantFacts
                        facts={
                          Array.isArray(message.facts) ? message.facts : []
                        }
                        suggestedDraft={message.suggested_draft}
                        company={companyId}
                        onDraft={(value) => void reviewDraft(value, message)}
                        onProduct={(name) =>
                          void send(`Выбираю продукт: ${name}`)
                        }
                      />
                    ) : null}
                    <p>{message.content}</p>
                    {message.questions?.length ? (
                      <ul>
                        {message.questions.map((question) => (
                          <li key={question}>{question}</li>
                        ))}
                      </ul>
                    ) : null}
                    {message.reply_type === "missing_information" ? (
                      <div className={s.prompts}>
                        {products.data?.map((product) => (
                          <button
                            key={product.id}
                            disabled={busy || !!wait}
                            onClick={() =>
                              void send(`Выбираю продукт: ${product.name}`)
                            }
                          >
                            {product.name}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))}
                {busy ? <p role="status">Готовим объяснение…</p> : null}
              </div>
              <div className={s.composer}>
                {!messages.length ? (
                  <div id="saveliy-prompts" className={s.prompts}>
                    {prompts.map((prompt) => (
                      <button
                        key={prompt}
                        disabled={busy || !contextReady || !!wait}
                        onClick={() => void send(prompt)}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                ) : null}
                {error ? <Notice tone="error">{error}</Notice> : null}
                <p className={s.hint} role="status">
                  {wait
                    ? `Повторная отправка доступна через ${wait} с.`
                    : announcement}
                </p>
                <Textarea
                  label="Сообщение Савелию"
                  aria-label="Сообщение Савелию"
                  labelView="outer"
                  block
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  maxLength={2000}
                  disabled={busy || !contextReady}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      void send();
                    }
                  }}
                  placeholder="Вопрос о продукте или заявке"
                />
                <div className={s.sendRow}>
                  <small>
                    Только синтетические данные. Решение принимает банк.
                  </small>
                  <Button
                    size={40}
                    view="accent"
                    disabled={!draft.trim() || busy || !contextReady || !!wait}
                    onClick={() => void send()}
                  >
                    Отправить
                  </Button>
                </div>
              </div>
            </>
          )}
        </section>
      ) : null}
      <Dialog
        title="Проверить предложенные изменения"
        open={!!preview}
        onClose={() => setPreview(null)}
        footer={
          <>
            <Button onClick={() => setPreview(null)}>Отмена</Button>
            <Button view="accent" onClick={applyDraft}>
              Перенести в форму
            </Button>
          </>
        }
      >
        {preview ? (
          <>
            <p>
              Поля изменятся только в форме. Сохранение и отправку вы выполняете
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
                    {preview.before?.[key] || "Не задано"} →{" "}
                    {preview.value[key]}
                  </dd>
                </div>
              ))}
            </dl>
          </>
        ) : null}
      </Dialog>
    </>
  );
  return createPortal(widget, document.body);
}

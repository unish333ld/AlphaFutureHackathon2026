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
import { Button, Choice, Loading, Notice, Textarea } from "../shared/ui/kit";
import { AssistantFacts } from "./AssistantFacts";
import type { AssistantDraft } from "./assistantDraft";
import s from "./assistant.module.css";

type Geometry = { x: number; y: number; width: number; height: number };
type Drag = {
  kind: "move" | "resize";
  x: number;
  y: number;
  geometry: Geometry;
};
const minWidth = 380;
const minHeight = 420;
const mobile = () => window.innerWidth <= 700;
const fit = (value: Geometry): Geometry => {
  const viewportWidth = window.visualViewport?.width ?? window.innerWidth;
  const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
  const left = window.visualViewport?.offsetLeft ?? 0;
  const top = window.visualViewport?.offsetTop ?? 0;
  const availableWidth = Math.max(1, viewportWidth - 16);
  const availableHeight = Math.max(1, viewportHeight - 16);
  const width = Math.min(
    Math.max(Math.min(minWidth, availableWidth), value.width),
    availableWidth,
  );
  const height = Math.min(
    Math.max(Math.min(minHeight, availableHeight), value.height),
    availableHeight,
  );
  return {
    width,
    height,
    x: Math.max(left + 8, Math.min(value.x, left + viewportWidth - width - 8)),
    y: Math.max(top + 8, Math.min(value.y, top + viewportHeight - height - 8)),
  };
};
const initialGeometry = (): Geometry => {
  const width = Math.min(780, Math.max(1, window.innerWidth - 32));
  const height = Math.min(600, Math.max(1, window.innerHeight - 32));
  return fit({
    width,
    height,
    x: window.innerWidth - width - 24,
    y: window.innerHeight - height - 24,
  });
};
const readGeometry = (userId: string): Geometry => {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(`saveliy:window:${userId}`) ?? "null",
    );
    if (value && typeof value === "object") {
      const item = value as Partial<Geometry>;
      if (
        [item.x, item.y, item.width, item.height].every(
          (n) => typeof n === "number" && Number.isFinite(n),
        )
      )
        return fit(item as Geometry);
    }
  } catch {
    // Browser storage can be disabled; the window still works.
  }
  return initialGeometry();
};
const shortDate = (value: string) =>
  new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
const commonPrompts = [
  "Какой кредит подойдёт для моего бизнеса?",
  "Сколько составит примерный ежемесячный платёж?",
  "Какие данные нужны для заявки?",
  "Что происходит с моей заявкой?",
];

export default function AssistantWidget() {
  const { user } = useAuth();
  const userId = user!.id;
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const { companies } = useCatalogs();
  const trigger = useRef<HTMLButtonElement>(null);
  const windowNode = useRef<HTMLElement>(null);
  const messagesNode = useRef<HTMLDivElement>(null);
  const animation = useRef<Animation | null>(null);
  const closing = useRef(false);
  const drag = useRef<Drag | null>(null);
  const loadId = useRef(0);
  const [open, setOpen] = useState(false);
  const [promptsOpen, setPromptsOpen] = useState(true);
  const [geometry, setGeometry] = useState(() => readGeometry(userId));
  const [historyOpen, setHistoryOpen] = useState(false);
  const [companyChoice, setCompanyChoice] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [oldestPage, setOldestPage] = useState(1);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [historyError, setHistoryError] = useState<unknown>(null);

  const applicationId = /^\/app\/loans\/([0-9a-f-]{36})(?:\/|$)/i.exec(
    location.pathname,
  )?.[1];
  const routeApplication = useQuery({
    queryKey: ["user", userId, "assistant", "route-application", applicationId],
    queryFn: ({ signal }) => api.application(applicationId!, false, signal),
    enabled: open && !!applicationId,
  });
  const history = useQuery({
    queryKey: ["user", userId, "assistant", "conversations", historyPage],
    queryFn: ({ signal }) => api.assistantConversations(historyPage, signal),
    enabled: open,
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
    companyChoice ||
    routeApplication.data?.company ||
    companies.data?.[0]?.id ||
    "";
  const applicationContext =
    conversation?.application ||
    (routeApplication.data?.company === companyId
      ? routeApplication.data.id
      : undefined);
  const companyName =
    companies.data?.find((item) => item.id === companyId)?.name ?? "Компания";
  const prompts = applicationContext
    ? [
        ...commonPrompts,
        "Какой сейчас статус и что мне делать дальше?",
        "Объясни решение по моей заявке",
      ]
    : commonPrompts;

  useEffect(() => {
    if (routeApplication.data && !selectedId)
      setCompanyChoice(routeApplication.data.company);
  }, [routeApplication.data, selectedId]);
  useEffect(() => {
    const onResize = () => setGeometry((current) => fit(current));
    window.addEventListener("resize", onResize);
    window.visualViewport?.addEventListener("resize", onResize);
    window.visualViewport?.addEventListener("scroll", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.visualViewport?.removeEventListener("resize", onResize);
      window.visualViewport?.removeEventListener("scroll", onResize);
    };
  }, []);
  useLayoutEffect(() => {
    if (!open || !windowNode.current || !trigger.current || closing.current)
      return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const panel = windowNode.current.getBoundingClientRect();
    const button = trigger.current.getBoundingClientRect();
    animation.current?.cancel();
    animation.current = windowNode.current.animate(
      [
        {
          transform: `translate(${button.left - panel.left}px, ${button.top - panel.top}px) scale(${button.width / panel.width}, ${button.height / panel.height})`,
          opacity: 0.25,
        },
        { transform: "translate(0, 0) scale(1)", opacity: 1 },
      ],
      { duration: 340, easing: "cubic-bezier(.22, 1, .36, 1)" },
    );
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        close();
      }
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [open]);
  useEffect(() => {
    try {
      localStorage.setItem(
        `saveliy:window:${userId}`,
        JSON.stringify(geometry),
      );
    } catch {
      // Position persistence is optional.
    }
  }, [geometry, userId]);
  useEffect(() => {
    if (messagesNode.current)
      messagesNode.current.scrollTop = messagesNode.current.scrollHeight;
  }, [messages.length, busy]);

  const loadMessages = useCallback(async (id: string) => {
    const requestId = ++loadId.current;
    setLoadingMessages(true);
    setHistoryError(null);
    try {
      const first = await api.assistantMessages(id);
      const lastPage = Math.max(1, Math.ceil(first.count / 25));
      const last =
        lastPage === 1 ? first : await api.assistantMessages(id, lastPage);
      if (requestId !== loadId.current) return;
      setMessages(last.results);
      setOldestPage(lastPage);
    } catch (cause) {
      if (requestId === loadId.current) setHistoryError(cause);
    } finally {
      if (requestId === loadId.current) setLoadingMessages(false);
    }
  }, []);
  useEffect(() => {
    if (open && selectedId) void loadMessages(selectedId);
    else if (!selectedId) {
      loadId.current++;
      setMessages([]);
    } else loadId.current++;
  }, [open, selectedId, loadMessages]);

  async function loadOlder() {
    if (!selectedId || oldestPage <= 1) return;
    try {
      const previous = await api.assistantMessages(selectedId, oldestPage - 1);
      setMessages((current) => [...previous.results, ...current]);
      setOldestPage((page) => page - 1);
    } catch (cause) {
      setHistoryError(cause);
    }
  }
  function close() {
    if (closing.current) return;
    const panel = windowNode.current;
    const button = trigger.current;
    const finish = () => {
      closing.current = false;
      setOpen(false);
      requestAnimationFrame(() =>
        trigger.current?.focus({ preventScroll: true }),
      );
    };
    if (
      !panel ||
      !button ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      finish();
      return;
    }
    closing.current = true;
    animation.current?.cancel();
    const from = panel.getBoundingClientRect();
    const to = button.getBoundingClientRect();
    animation.current = panel.animate(
      [
        { transform: "translate(0, 0) scale(1)", opacity: 1 },
        {
          transform: `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${to.width / from.width}, ${to.height / from.height})`,
          opacity: 0.2,
        },
      ],
      { duration: 320, easing: "cubic-bezier(.64, 0, .78, 0)" },
    );
    animation.current.finished.then(finish).catch(() => {
      closing.current = false;
    });
  }
  function newChat() {
    setSelectedId(null);
    setMessages([]);
    setError(null);
    setHistoryOpen(false);
  }
  async function send() {
    const text = draft.trim();
    if (!text || text.length > 2000 || !companyId || busy) return;
    setBusy(true);
    setError(null);
    let targetId = selectedId;
    try {
      let current: AssistantConversation;
      if (selectedId) {
        if (!conversation) throw new Error("Диалог ещё загружается.");
        current = conversation;
      } else {
        current = await api.assistantCreateConversation(
          companyId,
          applicationContext,
        );
        targetId = current.id;
        setSelectedId(current.id);
        client.setQueryData(
          ["user", userId, "assistant", "conversation", current.id],
          current,
        );
      }
      const reply = await api.assistantSend(current.id, text, current.version);
      client.setQueryData(
        ["user", userId, "assistant", "conversation", current.id],
        {
          ...current,
          version: reply.version,
        },
      );
      setDraft("");
      await loadMessages(current.id);
      await client.invalidateQueries({
        queryKey: ["user", userId, "assistant", "conversations"],
      });
      setHistoryPage(1);
    } catch (cause) {
      setError(cause);
      if (
        targetId &&
        cause instanceof ApiError &&
        [0, 409, 503].includes(cause.status)
      ) {
        await client.invalidateQueries({
          queryKey: ["user", userId, "assistant", "conversation", targetId],
        });
        await loadMessages(targetId);
      }
    } finally {
      setBusy(false);
    }
  }
  function onDraft(value: AssistantDraft) {
    close();
    navigate("/app/loans/new", { state: { assistantDraft: value } });
  }
  function pointerStart(
    event: React.PointerEvent<HTMLElement>,
    kind: Drag["kind"],
  ) {
    if (mobile()) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { kind, x: event.clientX, y: event.clientY, geometry };
  }
  function pointerMove(event: React.PointerEvent<HTMLElement>) {
    const start = drag.current;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    setGeometry(
      fit(
        start.kind === "move"
          ? {
              ...start.geometry,
              x: start.geometry.x + dx,
              y: start.geometry.y + dy,
            }
          : {
              ...start.geometry,
              width: start.geometry.width + dx,
              height: start.geometry.height + dy,
            },
      ),
    );
  }
  function pointerEnd() {
    drag.current = null;
  }

  return createPortal(
    <>
      <div className={s.launcher}>
        <Button
          ref={trigger}
          size={40}
          view="accent"
          onClick={() => {
            if (open) close();
            else setOpen(true);
          }}
          aria-expanded={open}
        >
          Савелий
        </Button>
      </div>
      {open ? (
        <section
          ref={windowNode}
          className={s.window}
          style={{
            left: geometry.x,
            top: geometry.y,
            width: geometry.width,
            height: geometry.height,
          }}
          role="dialog"
          aria-modal="false"
          aria-label="Савелий, помощник по кредиту"
        >
          <div className={s.header}>
            <div
              className={s.grab}
              tabIndex={0}
              aria-label="Переместить окно Савелия стрелками"
              onPointerDown={(event) => pointerStart(event, "move")}
              onPointerMove={pointerMove}
              onPointerUp={pointerEnd}
              onKeyDown={(event) => {
                const movement: Record<string, [number, number]> = {
                  ArrowLeft: [-20, 0],
                  ArrowRight: [20, 0],
                  ArrowUp: [0, -20],
                  ArrowDown: [0, 20],
                };
                const step = movement[event.key];
                if (step && !mobile()) {
                  event.preventDefault();
                  setGeometry((current) =>
                    fit({
                      ...current,
                      x: current.x + step[0],
                      y: current.y + step[1],
                    }),
                  );
                }
              }}
            >
              <strong>Савелий</strong>
              <small>ИИ-помощник, демо</small>
            </div>
            <button type="button" onClick={close} aria-label="Свернуть Савелия">
              _
            </button>
            <button
              type="button"
              onClick={() => setGeometry(initialGeometry())}
              aria-label="Вернуть размер и положение"
            >
              ↺
            </button>
            <button type="button" onClick={close} aria-label="Закрыть Савелия">
              ×
            </button>
          </div>
          <div className={s.body}>
            <aside
              className={`${s.sidebar} ${historyOpen ? s.sidebarOpen : ""}`}
              aria-label="История диалогов"
            >
              <Button size={40} block onClick={newChat}>
                Новый чат
              </Button>
              <div className={s.historyList}>
                {history.isPending ? (
                  <Loading label="Загружаем диалоги…" />
                ) : null}
                {history.isError ? (
                  <Notice tone="error">
                    Не удалось загрузить историю.{" "}
                    <button onClick={() => void history.refetch()}>
                      Повторить
                    </button>
                  </Notice>
                ) : null}
                {history.data?.results.length === 0 ? (
                  <p className={s.hint}>Диалогов пока нет.</p>
                ) : null}
                {history.data?.results.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`${s.historyItem} ${selectedId === item.id ? s.historySelected : ""}`}
                    aria-current={selectedId === item.id ? "true" : undefined}
                    onClick={() => {
                      setSelectedId(item.id);
                      setError(null);
                      setHistoryOpen(false);
                    }}
                  >
                    <strong>
                      {companies.data?.find(
                        (company) => company.id === item.company,
                      )?.name ?? "Компания"}
                    </strong>
                    <small>
                      {item.application ? "По заявке, " : "Общий чат, "}
                      {shortDate(item.updated_at)}
                    </small>
                  </button>
                ))}
              </div>
              {history.data && (history.data.previous || history.data.next) ? (
                <div className={s.pageButtons}>
                  <button
                    disabled={!history.data.previous}
                    onClick={() => setHistoryPage((p) => p - 1)}
                  >
                    Назад
                  </button>
                  <span>{historyPage}</span>
                  <button
                    disabled={!history.data.next}
                    onClick={() => setHistoryPage((p) => p + 1)}
                  >
                    Далее
                  </button>
                </div>
              ) : null}
            </aside>
            <div className={s.chat}>
              <div className={s.context}>
                <button
                  type="button"
                  className={s.historyToggle}
                  onClick={() => setHistoryOpen((v) => !v)}
                  aria-expanded={historyOpen}
                >
                  История
                </button>
                {selectedId ? (
                  <div>
                    <strong>{companyName}</strong>
                    <small>
                      {conversation?.application
                        ? "Диалог по заявке"
                        : "Общий диалог"}
                    </small>
                  </div>
                ) : companies.data?.length ? (
                  <Choice
                    label="Компания для нового чата"
                    value={companyId}
                    onChange={setCompanyChoice}
                    options={companies.data.map((item) => ({
                      key: item.id,
                      content: item.name,
                    }))}
                  />
                ) : (
                  <span>Нет доступной компании</span>
                )}
              </div>
              <div ref={messagesNode} className={s.messages} aria-live="polite">
                {!selectedId ? (
                  <div className={s.welcome}>
                    <strong>Здравствуйте! Я Савелий.</strong>
                    <p>
                      Помогу разобраться в демо-продуктах и вашей заявке.
                      Выберите вопрос или напишите свой.
                    </p>
                  </div>
                ) : loadingMessages ? (
                  <Loading label="Загружаем сообщения…" />
                ) : null}
                {historyError ? (
                  <Notice tone="error">
                    Не удалось загрузить сообщения.{" "}
                    <button
                      onClick={() =>
                        selectedId && void loadMessages(selectedId)
                      }
                    >
                      Повторить
                    </button>
                  </Notice>
                ) : null}
                {selectedId && oldestPage > 1 ? (
                  <button className={s.older} onClick={() => void loadOlder()}>
                    Показать более ранние
                  </button>
                ) : null}
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`${s.message} ${message.role === "user" ? s.userMessage : s.assistantMessage}`}
                  >
                    <strong>
                      {message.role === "user" ? "Вы" : "Савелий"}
                    </strong>
                    <p>{message.content}</p>
                    {message.role === "assistant" ? (
                      <AssistantFacts
                        facts={
                          Array.isArray(message.facts) ? message.facts : []
                        }
                        suggestedDraft={message.suggested_draft}
                        company={companyId}
                        onDraft={onDraft}
                      />
                    ) : null}
                  </div>
                ))}
                {busy ? <Loading label="Савелий готовит ответ…" /> : null}
              </div>
              <div className={s.composer}>
                <div className={s.promptRow}>
                  <button
                    type="button"
                    className={s.promptToggle}
                    onClick={() => setPromptsOpen((value) => !value)}
                    aria-label={
                      promptsOpen
                        ? "Свернуть частые вопросы"
                        : "Развернуть частые вопросы"
                    }
                    aria-expanded={promptsOpen}
                    aria-controls="saveliy-prompts"
                  >
                    {promptsOpen ? "‹" : "›"}
                  </button>
                  <div
                    id="saveliy-prompts"
                    className={s.prompts}
                    hidden={!promptsOpen}
                    onWheel={(event) => {
                      const node = event.currentTarget;
                      if (node.scrollWidth > node.clientWidth && event.deltaY) {
                        event.preventDefault();
                        node.scrollLeft += event.deltaY;
                      }
                    }}
                  >
                    {prompts.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => setDraft(prompt)}
                        disabled={busy}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
                {error ? (
                  <Notice tone="error">
                    {error instanceof ApiError
                      ? error.message
                      : "Не удалось получить ответ. Проверьте историю диалога."}{" "}
                    {error instanceof ApiError &&
                    [0, 409, 503].includes(error.status)
                      ? "История обновлена; проверьте её перед повтором."
                      : null}
                  </Notice>
                ) : null}
                <Textarea
                  label="Сообщение Савелию"
                  aria-label="Сообщение Савелию"
                  labelView="outer"
                  block
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
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
                  maxLength={2000}
                  disabled={busy || !companyId}
                  placeholder="Напишите вопрос о продукте или заявке"
                />
                <div className={s.sendRow}>
                  <small>Синтетические данные, решение принимает банк</small>
                  <Button
                    size={40}
                    view="accent"
                    disabled={!draft.trim() || busy || !companyId}
                    onClick={() => void send()}
                  >
                    Отправить
                  </Button>
                </div>
              </div>
            </div>
          </div>
          <button
            className={s.resize}
            type="button"
            aria-label="Изменить размер окна Савелия"
            onPointerDown={(event) => pointerStart(event, "resize")}
            onPointerMove={pointerMove}
            onPointerUp={pointerEnd}
            onKeyDown={(event) => {
              const step: Record<string, [number, number]> = {
                ArrowLeft: [-20, 0],
                ArrowRight: [20, 0],
                ArrowUp: [0, -20],
                ArrowDown: [0, 20],
              };
              const delta = step[event.key];
              if (delta && !mobile()) {
                event.preventDefault();
                setGeometry((current) =>
                  fit({
                    ...current,
                    width: current.width + delta[0],
                    height: current.height + delta[1],
                  }),
                );
              }
            }}
          />
        </section>
      ) : null}
    </>,
    document.body,
  );
}

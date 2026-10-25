import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { Button } from "@alfalab/core-components/button";
import { Input } from "@alfalab/core-components/input";
import { Select } from "@alfalab/core-components/select";
import { Checkbox } from "@alfalab/core-components/checkbox";
import { Modal } from "@alfalab/core-components/modal";
import { Textarea } from "@alfalab/core-components/textarea";
import { ApiError } from "../api/errors";
import { statuses } from "../../entities/credit";
import type { Status } from "../api/client";
import s from "./kit.module.css";

export { Button, Input, Checkbox, Textarea };
export function Choice({
  label,
  value,
  onChange,
  options,
  disabled,
  error,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { key: string; content: string }[];
  disabled?: boolean;
  error?: string;
  hint?: string;
}) {
  const id = useId();
  const allKey = "__all__";
  const hasAll = options.some((option) => option.key === "");
  const wrapper = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Core Select 50.38 labels the native field but omits the outer combobox name.
    // Add only its accessible name; leave keyboard/selection behaviour to Core.
    const node = wrapper.current;
    const name = () =>
      node?.firstElementChild?.setAttribute("aria-label", label);
    name();
    const observer = new MutationObserver(name);
    if (node) observer.observe(node, { childList: true });
    return () => observer.disconnect();
  }, [label]);
  return (
    <div ref={wrapper}>
      <Select
        id={id}
        label={label}
        labelView="outer"
        options={options.map((option) => ({
          ...option,
          key: option.key || allKey,
        }))}
        selected={value || (hasAll ? allKey : null)}
        onChange={({ selected }) =>
          onChange(selected?.key === allKey ? "" : (selected?.key ?? ""))
        }
        block
        size={48}
        nativeSelect
        Arrow={() => <span aria-hidden="true">⌄</span>}
        disabled={disabled}
        error={error}
        hint={hint}
        placeholder="Выберите вариант"
      />
    </div>
  );
}
export function Panel({
  title,
  children,
  className = "",
  action,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <section className={`${s.panel} ${className}`}>
      {title ? (
        <div className={s.panelHeading}>
          <h2>{title}</h2>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}
export function Dialog({
  title,
  open,
  onClose,
  children,
  footer,
  busy = false,
  returnFocusRef,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  busy?: boolean;
  returnFocusRef?: RefObject<HTMLElement>;
}) {
  const id = useId();
  return (
    <Modal
      open={open}
      onClose={() => {
        if (!busy) onClose();
      }}
      size={600}
      scrollLock
      onUnmount={() => {
        if (returnFocusRef)
          requestAnimationFrame(() => {
            const target = returnFocusRef.current;
            if (target?.isConnected) target.focus({ preventScroll: true });
            else
              document
                .getElementById("page-title")
                ?.focus({ preventScroll: true });
          });
      }}
      hasCloser={!busy}
      disableEscapeKeyDown={busy}
      disableBackdropClick={busy}
      wrapperProps={{
        "aria-labelledby": id,
        role: "dialog",
        "aria-modal": true,
      }}
    >
      <Modal.Header>
        <h2 id={id} className={s.dialogTitle}>
          {title}
        </h2>
      </Modal.Header>
      <Modal.Content>
        <div className={s.dialogBody}>{children}</div>
      </Modal.Content>
      {footer ? (
        <Modal.Footer>
          <div className={s.dialogFooter}>{footer}</div>
        </Modal.Footer>
      ) : null}
    </Modal>
  );
}
export function Notice({
  children,
  tone = "info",
  title,
}: {
  children: ReactNode;
  tone?: "info" | "warning" | "success" | "error";
  title?: string;
}) {
  return (
    <div
      className={`${s.notice} ${s[tone]}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {title ? <strong>{title}</strong> : null}
      <div>{children}</div>
    </div>
  );
}
export function useRetryCooldown(error: unknown) {
  const retryAfter = error instanceof ApiError ? error.retryAfter : 0;
  const [remaining, setRemaining] = useState(retryAfter);
  useEffect(() => {
    setRemaining(retryAfter);
    if (!retryAfter) return;
    const timer = setInterval(
      () => setRemaining((v) => Math.max(0, v - 1)),
      1000,
    );
    return () => clearInterval(timer);
  }, [error, retryAfter]);
  return remaining;
}
export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const remaining = useRetryCooldown(error);
  return (
    <Notice tone="error" title="Не удалось выполнить действие">
      <p>
        {error instanceof ApiError
          ? error.message
          : "Возникла ошибка. Попробуйте обновить данные."}
      </p>
      {error instanceof ApiError &&
      Object.keys(error.normalized.fields).length ? (
        <ul>
          {Object.entries(error.normalized.fields).map(([key, value]) => (
            <li key={key}>{value}</li>
          ))}
        </ul>
      ) : null}
      {remaining > 0 ? <p>Повтор доступен через {remaining} сек.</p> : null}
      {retry ? (
        <Button size={40} onClick={retry} disabled={remaining > 0}>
          Обновить данные
        </Button>
      ) : null}
    </Notice>
  );
}
export function Loading({ label = "Загружаем данные…" }: { label?: string }) {
  return (
    <div className={s.loading} role="status" aria-live="polite">
      <span className={s.spinner} aria-hidden="true" />
      {label}
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={s.empty}>
      <div className={s.emptyIcon} aria-hidden="true">
        ▤
      </div>
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}
export function Badge({ status }: { status: Status }) {
  const tone = ["issued"].includes(status)
    ? "success"
    : ["needs_info", "offered", "checking"].includes(status)
      ? "warning"
      : ["rejected", "expired"].includes(status)
        ? "error"
        : "neutral";
  return (
    <span className={`${s.badge} ${s[tone]}`}>
      <span aria-hidden="true">●</span>
      {statuses[status]}
    </span>
  );
}
export function Pagination({
  page,
  count,
  length,
  next,
  previous,
  onPage,
}: {
  page: number;
  count: number;
  length: number;
  next: string | null;
  previous: string | null;
  onPage: (page: number) => void;
}) {
  if (!count) return null;
  return (
    <nav aria-label="Страницы списка" className={s.pagination}>
      <span>
        {(page - 1) * 25 + 1}–{(page - 1) * 25 + length} из {count}
      </span>
      <div>
        <Button
          size={40}
          disabled={!previous}
          onClick={() => onPage(page - 1)}
          aria-label="Предыдущая страница"
        >
          Назад
        </Button>
        <Button
          size={40}
          disabled={!next}
          onClick={() => onPage(page + 1)}
          aria-label="Следующая страница"
        >
          Вперёд
        </Button>
      </div>
    </nav>
  );
}
export function Facts({
  rows,
}: {
  rows: { label: string; value: ReactNode }[];
}) {
  return (
    <dl className={s.facts}>
      {rows.map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

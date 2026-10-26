import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useAuth } from "../app/auth";
import type { Application } from "../shared/api/client";
import { currentOffer, money } from "../entities/credit";
import { Button, Dialog } from "../shared/ui/kit";
import s from "./agreement.module.css";

export function CompletionDialog({
  open,
  title,
  children,
  onClose,
  animated = false,
  returnFocusRef,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  animated?: boolean;
  returnFocusRef?: RefObject<HTMLElement>;
}) {
  const body = useRef<HTMLDivElement>(null);
  const paused = useRef(false);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    paused.current = false;
    // Announce the result, not an automatically focused destructive control.
    const focus = setTimeout(() => body.current?.focus(), 0);
    const interaction = (event: Event) => {
      const dialog = body.current?.closest('[role="dialog"]');
      if (
        event.target instanceof Node &&
        dialog?.contains(event.target) &&
        event.target !== dialog &&
        event.target !== body.current
      )
        paused.current = true;
    };
    document.addEventListener("focusin", interaction);
    document.addEventListener("pointerdown", interaction);
    document.addEventListener("keydown", interaction);
    const timer = setTimeout(() => {
      if (!paused.current) close.current();
    }, 2700);
    return () => {
      clearTimeout(focus);
      clearTimeout(timer);
      document.removeEventListener("focusin", interaction);
      document.removeEventListener("pointerdown", interaction);
      document.removeEventListener("keydown", interaction);
    };
  }, [open]);
  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      returnFocusRef={returnFocusRef}
      footer={<Button onClick={onClose}>Закрыть</Button>}
    >
      <div
        ref={body}
        tabIndex={0}
        data-autofocus
        className={s.completion}
        onPointerDown={() => {
          paused.current = true;
        }}
        onKeyDown={() => {
          paused.current = true;
        }}
        onFocusCapture={(event) => {
          if (event.target !== body.current) paused.current = true;
        }}
      >
        {animated ? (
          <div className={s.celebration} aria-hidden="true">
            <span className={s.check}>✓</span>
            {Array.from({ length: 6 }, (_, index) => (
              <i key={index} className={s.particle} />
            ))}
          </div>
        ) : null}
        <div aria-live="polite">{children}</div>
      </div>
    </Dialog>
  );
}

export function IssuanceFeedback({ app }: { app: Application }) {
  const { user } = useAuth();
  const result = currentOffer(app)?.agreement?.disbursement;
  const initial = useRef(result?.id ?? null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!result || !user || initial.current === result.id) return;
    initial.current = result.id;
    const key = `credit:issued-seen:${user.id}:${result.id}`;
    try {
      if (sessionStorage.getItem(key)) return;
      sessionStorage.setItem(key, "1");
    } catch {
      /* The in-memory guard still prevents refetch repeats. */
    }
    setOpen(true);
  }, [result, user]);
  return (
    <CompletionDialog
      open={open}
      onClose={() => setOpen(false)}
      title="Демо-выдача завершена"
      animated
    >
      <p>
        <strong>{money(result?.amount)}</strong>
      </p>
      <p>Реального перевода денег не было.</p>
    </CompletionDialog>
  );
}

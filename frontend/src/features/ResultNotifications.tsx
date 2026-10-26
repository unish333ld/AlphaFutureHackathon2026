import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../app/auth";
import { api, type Schema } from "../shared/api/client";
import { ApiError } from "../shared/api/errors";
import s from "./resultNotifications.module.css";

type Result = Schema["ResultNotification"];
const titles: Record<Result["kind"], string> = {
  needs_info: "Проверьте данные заявки",
  approved: "Заявка одобрена",
  counteroffer: "Предложены другие условия",
  rejected: "По заявке принято решение об отказе",
  offered: "По заявке есть решение",
};

export function ResultNotifications() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [current, setCurrent] = useState<Result | null>(null);
  const [leaving, setLeaving] = useState(false);
  const pending = useRef<Result[]>([]);
  const currentRef = useRef<Result | null>(null);
  const timer = useRef<number | null>(null);
  const exitTimer = useRef<number | null>(null);
  const hovered = useRef(false);
  const focused = useRef(false);
  const key = user ? `credit-results:${user.id}` : "";
  function clearTimer() {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }
  function pause() {
    clearTimer();
    if (exitTimer.current !== null) {
      window.clearTimeout(exitTimer.current);
      exitTimer.current = null;
      setLeaving(false);
    }
  }
  function schedule() {
    clearTimer();
    if (!hovered.current && !focused.current)
      timer.current = window.setTimeout(() => dismiss(), 2000);
  }
  function showNext() {
    const next = pending.current.shift() ?? null;
    if (!next || !currentRef.current) {
      hovered.current = false;
      focused.current = false;
    }
    currentRef.current = next;
    setCurrent(next);
    setLeaving(false);
    if (next) schedule();
  }
  function dismiss() {
    clearTimer();
    if (!currentRef.current || exitTimer.current !== null) return;
    setLeaving(true);
    exitTimer.current = window.setTimeout(() => {
      exitTimer.current = null;
      showNext();
    }, 180);
  }
  useEffect(() => {
    if (!user || user.system_role !== "client") return;
    const controller = new AbortController();
    let timeout: number | undefined;
    const poll = async () => {
      if (document.visibilityState === "hidden") {
        timeout = window.setTimeout(() => void poll(), 5000);
        return;
      }
      try {
        let cursor = sessionStorage.getItem(key) || undefined;
        for (let page = 0; page < 5; page++) {
          const batch = await api.notifications(cursor, controller.signal);
          if (controller.signal.aborted) return;
          cursor = batch.cursor;
          sessionStorage.setItem(key, cursor);
          for (const item of batch.results) {
            if (
              item.id !== currentRef.current?.id &&
              !pending.current.some((queued) => queued.id === item.id)
            )
              pending.current.push(item);
          }
          if (batch.results.length) {
            void cache.invalidateQueries({
              queryKey: ["user", user.id],
              predicate: (query) =>
                ["application", "applications", "events"].some((part) =>
                  query.queryKey.includes(part),
                ),
            });
            if (!currentRef.current) showNext();
          }
          if (!batch.has_more) break;
        }
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 400)
          sessionStorage.removeItem(key);
      }
      if (!controller.signal.aborted)
        timeout = window.setTimeout(() => void poll(), 5000);
    };
    void poll();
    return () => {
      controller.abort();
      window.clearTimeout(timeout);
      clearTimer();
      if (exitTimer.current !== null) window.clearTimeout(exitTimer.current);
      exitTimer.current = null;
      hovered.current = false;
      focused.current = false;
      pending.current = [];
      currentRef.current = null;
      setCurrent(null);
    };
  }, [user?.id, user?.system_role, key, cache]);
  if (!current) return null;
  return (
    <aside
      className={`${s.toast} ${leaving ? s.leaving : ""}`}
      role="status"
      aria-live="polite"
      onPointerEnter={() => {
        hovered.current = true;
        pause();
      }}
      onPointerLeave={() => {
        hovered.current = false;
        schedule();
      }}
      onFocusCapture={() => {
        focused.current = true;
        pause();
      }}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) {
          focused.current = false;
          schedule();
        }
      }}
    >
      <div>
        <strong>{titles[current.kind]}</strong>
        <p>Заявка {current.number}</p>
        <Link to={`/app/loans/${current.application_id}`} onClick={dismiss}>
          Открыть заявку
        </Link>
      </div>
      <button type="button" aria-label="Закрыть уведомление" onClick={dismiss}>
        Закрыть
      </button>
    </aside>
  );
}

import { useRef, type ReactNode } from "react";
import { Link, useBeforeUnload, useBlocker } from "react-router-dom";
import { Button, Dialog } from "./kit";

export function LinkButton({
  to,
  children,
  view = "secondary",
  size = 48,
}: {
  to: string;
  children: ReactNode;
  view?: "accent" | "secondary" | "outlined" | "text";
  size?: 32 | 40 | 48 | 56;
}) {
  return (
    <Button Component={Link} href={to} view={view} size={size}>
      {children}
    </Button>
  );
}
export function useUnsavedGuard(dirty: boolean) {
  const allowed = useRef(false);
  const blocker = useBlocker(() => dirty && !allowed.current);
  useBeforeUnload((event) => {
    if (dirty && !allowed.current) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  const dialog = (
    <Dialog
      title="Выйти без сохранения?"
      open={blocker.state === "blocked"}
      onClose={() => blocker.reset?.()}
      footer={
        <>
          <Button onClick={() => blocker.reset?.()}>Вернуться к форме</Button>
          <Button view="accent" onClick={() => blocker.proceed?.()}>
            Выйти без сохранения
          </Button>
        </>
      }
    >
      <p>
        Несохранённые изменения будут потеряны. Сохранённый на сервере черновик
        останется доступен.
      </p>
    </Dialog>
  );
  return {
    dialog,
    allowNavigation: () => {
      allowed.current = true;
    },
  };
}

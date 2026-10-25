import { useEffect, useRef, type ReactNode } from "react";
import s from "../../app/layout.module.css";
export function PageTitle({
  title,
  subtitle,
  action,
  eyebrow,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  eyebrow?: string;
}) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    document.title = `${title}, Кредитный кабинет`;
    ref.current?.focus({ preventScroll: true });
  }, [title]);
  return (
    <div className={s.pageHeading}>
      <div>
        {eyebrow ? <div className={s.eyebrow}>{eyebrow}</div> : null}
        <h1 id="page-title" tabIndex={-1} ref={ref}>
          {title}
        </h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

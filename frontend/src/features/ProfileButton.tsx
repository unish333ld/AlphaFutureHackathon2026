import { useRef, useState } from "react";
import { UserMIcon } from "@alfalab/icons-glyph/UserMIcon";
import { useAuth } from "../app/auth";
import { useCatalogs } from "../app/queries";
import { displayName } from "../entities/credit";
import { Dialog, ErrorNotice, Facts, Loading } from "../shared/ui/kit";
import s from "../app/layout.module.css";

export function ProfileButton() {
  const { user } = useAuth();
  const { companies } = useCatalogs();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  if (!user) return null;
  const name =
    [user.first_name, user.last_name].filter(Boolean).join(" ") ||
    user.username;
  const memberships =
    companies.data?.filter((company) =>
      user.memberships.some(
        (member) => member.active && member.company === company.id,
      ),
    ) ?? [];
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={s.profileButton}
        onClick={() => setOpen(true)}
        aria-label={`Профиль: ${name}`}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span className={s.avatar} aria-hidden="true">
          <UserMIcon />
        </span>
        <span className={s.accountName}>
          <strong className={s.accountNameDesktop}>{name}</strong>
          <strong className={s.mobileProfileLabel}>Профиль</strong>
          <small>
            {user.system_role === "specialist"
              ? "Кредитный специалист"
              : "Представитель компании"}
          </small>
        </span>
      </button>
      <Dialog
        title="Профиль"
        open={open}
        onClose={() => setOpen(false)}
        returnFocusRef={trigger}
      >
        <Facts
          rows={[
            { label: "Имя", value: name },
            { label: "Логин", value: user.username },
            {
              label: "Роль",
              value:
                user.system_role === "specialist"
                  ? "Кредитный специалист"
                  : "Представитель компании",
            },
          ]}
        />
        {user.system_role === "client" ? (
          companies.isPending ? (
            <Loading label="Загружаем компании…" />
          ) : companies.isError ? (
            <ErrorNotice
              error={companies.error}
              retry={() => {
                void companies.refetch();
              }}
            />
          ) : memberships.length ? (
            memberships.map((company) => (
              <div key={company.id} className={s.profileCompany}>
                <strong>{displayName(company.name)}</strong>
                <span>ИНН {company.inn}</span>
              </div>
            ))
          ) : (
            <p>Доступных компаний нет.</p>
          )
        ) : null}
      </Dialog>
    </>
  );
}

import { Navigate } from "react-router-dom";
import { AlfaBankLIcon } from "@alfalab/icons-logotype/AlfaBankLIcon";
import { useAuth } from "../app/auth";
import LoginForm from "../features/LoginForm";
import { ErrorNotice, Loading } from "../shared/ui/kit";
import s from "../app/layout.module.css";
export default function LoginPage() {
  const auth = useAuth();
  if (auth.loading) return <Loading label="Проверяем сессию…" />;
  if (auth.user)
    return (
      <Navigate
        to={auth.user.system_role === "specialist" ? "/staff" : "/app"}
        replace
      />
    );
  return (
    <main className={s.loginPage}>
      <div className={s.loginIntro}>
        <div className={s.brand}>
          <AlfaBankLIcon
            className={s.brandMark}
            aria-hidden="true"
            width={26}
            height={40}
          />
          <span>
            Альфа Хак 2026<small>КРЕДИТНЫЙ КАБИНЕТ</small>
          </span>
        </div>
        <h1>Кредитный кабинет для бизнеса</h1>
        <p>Создайте заявку, проверьте решение и условия кредита.</p>
        <p className={s.muted}>
          Тестовый режим. Данные компаний синтетические.
        </p>
      </div>
      <div className={s.loginCard}>
        <h2>Вход в кабинет</h2>
        {auth.startupError ? (
          <ErrorNotice
            error={auth.startupError}
            retry={() => {
              void auth.check();
            }}
          />
        ) : null}
        <LoginForm />
      </div>
    </main>
  );
}

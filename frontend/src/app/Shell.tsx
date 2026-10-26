import { useEffect, useRef, useState } from "react";
import { AlfaBankLIcon } from "@alfalab/icons-logotype/AlfaBankLIcon";
import { BurgerMIcon } from "@alfalab/icons-glyph/BurgerMIcon";
import { LogOutMIcon } from "@alfalab/icons-glyph/LogOutMIcon";
import {
  Navigate,
  NavLink,
  Outlet,
  ScrollRestoration,
  useLocation,
} from "react-router-dom";
import { useAuth } from "./auth";
import { Button, Dialog, ErrorNotice, Loading } from "../shared/ui/kit";
import LoginForm from "../features/LoginForm";
import AssistantWidget from "../features/AssistantWidget";
import { AssistantFormProvider } from "../features/AssistantFormContext";
import { ProfileButton } from "../features/ProfileButton";
import { ResultNotifications } from "../features/ResultNotifications";
import s from "./layout.module.css";

export default function Shell() {
  const auth = useAuth();
  const location = useLocation();
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [leaving, setLeaving] = useState(false);
  const [logoutDialog, setLogoutDialog] = useState(false);
  const logoutTrigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setMenu(false);
    document.getElementById("page-title")?.focus();
  }, [location.pathname]);
  if (auth.loading) return <Loading label="Проверяем сессию…" />;
  if (!auth.user)
    return auth.startupError ? (
      <main className={s.loginPage}>
        <ErrorNotice
          error={auth.startupError}
          retry={() => {
            void auth.check();
          }}
        />
      </main>
    ) : (
      <Navigate to="/login" replace />
    );
  const staff = auth.user.system_role === "specialist";
  const home = staff ? "/staff" : "/app";
  async function logout() {
    setLeaving(true);
    setError(null);
    try {
      await auth.logout();
    } catch (cause) {
      setError(cause);
    } finally {
      setLeaving(false);
      setLogoutDialog(false);
    }
  }
  return (
    <AssistantFormProvider key={auth.user.id}>
      <div key={auth.user.id}>
        <a className={s.skipLink} href="#main-content">
          Перейти к содержимому
        </a>
        <header className={s.header}>
          <div className={s.headerInner}>
            <NavLink to={home} className={s.brand}>
              <AlfaBankLIcon
                className={s.brandMark}
                aria-hidden="true"
                width={26}
                height={40}
              />
              <span>
                Кредитный кабинет<small>АЛЬФА ХАК 2026</small>
              </span>
            </NavLink>
            <button
              className={s.menuButton}
              onClick={() => setMenu((v) => !v)}
              aria-expanded={menu}
              aria-controls="main-nav"
              aria-label="Меню"
            >
              <BurgerMIcon aria-hidden="true" />
            </button>
            <nav
              id="main-nav"
              aria-label="Основная навигация"
              className={`${s.nav} ${menu ? s.navOpen : ""}`}
            >
              {staff ? (
                <NavLink
                  to="/staff"
                  className={({ isActive }) => (isActive ? s.active : "")}
                >
                  Очередь заявок
                </NavLink>
              ) : (
                <>
                  <NavLink
                    end
                    to="/app"
                    className={({ isActive }) => (isActive ? s.active : "")}
                  >
                    Главная
                  </NavLink>
                  <NavLink
                    to="/app/loans"
                    className={({ isActive }) => (isActive ? s.active : "")}
                  >
                    Заявки и кредиты
                  </NavLink>
                </>
              )}
            </nav>
            <div className={s.account}>
              <ProfileButton />
              <Button
                ref={logoutTrigger}
                size={32}
                view="text"
                aria-label="Выйти из кабинета"
                title="Выйти из кабинета"
                onClick={() => setLogoutDialog(true)}
              >
                <LogOutMIcon aria-hidden="true" />
              </Button>
            </div>
          </div>
        </header>
        <main
          id="main-content"
          className={s.main}
          key={`${auth.user.id}:${auth.user.system_role}`}
        >
          {error ? <ErrorNotice error={error} /> : null}
          <Outlet />
        </main>
        <ScrollRestoration />
        <footer className={s.footer}>
          <span>Тестовый режим. Подпись и выдача без реальных операций.</span>
          <span>Альфа Хак 2026. Время — МСК.</span>
        </footer>
        {!staff && import.meta.env.VITE_AI_ASSISTANT_ENABLED === "true" ? (
          <AssistantWidget />
        ) : null}
        {!staff ? <ResultNotifications /> : null}
        <Dialog
          title="Выйти из кабинета?"
          open={logoutDialog}
          returnFocusRef={logoutTrigger}
          onClose={() => setLogoutDialog(false)}
          busy={leaving}
          footer={
            <>
              <Button onClick={() => setLogoutDialog(false)} disabled={leaving}>
                Остаться
              </Button>
              <Button
                view="accent"
                onClick={() => {
                  void logout();
                }}
                loading={leaving}
                disabled={leaving}
              >
                Завершить сессию
              </Button>
            </>
          }
        >
          <p>Несохранённый ввод будет удалён. Серверные заявки сохранятся.</p>
        </Dialog>
        <Dialog
          title="Сессия требует входа"
          open={auth.expired}
          busy
          onClose={() => {
            /* Keep the form mounted and locked until reauthentication. */
          }}
        >
          <p>
            Войдите снова. Ввод останется доступен при входе той же учётной
            записью; при смене пользователя кеш и формы очищаются.
          </p>
          <LoginForm reauth />
        </Dialog>
      </div>
    </AssistantFormProvider>
  );
}

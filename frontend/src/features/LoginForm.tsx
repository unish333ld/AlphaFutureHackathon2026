import { useId, useRef, useState, type FormEvent } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuth } from "../app/auth";
import { ApiError } from "../shared/api/errors";
import { Button, ErrorNotice, Input, useRetryCooldown } from "../shared/ui/kit";
import s from "../app/layout.module.css";

const schema = z.object({
  username: z
    .string()
    .trim()
    .min(1, "Введите логин")
    .max(150, "Не более 150 символов"),
  password: z
    .string()
    .min(1, "Введите пароль")
    .max(256, "Не более 256 символов"),
});
type Values = z.infer<typeof schema>;
export default function LoginForm({ reauth = false }: { reauth?: boolean }) {
  const auth = useAuth();
  const id = useId();
  const submitting = useRef(false);
  const [pending, setPending] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const cooldown = useRetryCooldown(error);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      username: reauth ? (auth.user?.username ?? "") : "",
      password: "",
    },
  });
  async function submit(values: Values) {
    if (cooldown || submitting.current) return;
    submitting.current = true;
    setPending(true);
    setError(null);
    try {
      await auth.login(values.username, values.password);
    } catch (cause) {
      setError(cause);
      form.setValue("password", "");
      setPasswordVisible(false);
      if (cause instanceof ApiError) {
        for (const name of ["username", "password"] as const) {
          const message = cause.normalized.fields[name];
          if (message) form.setError(name, { type: "server", message });
        }
      }
      requestAnimationFrame(() => form.setFocus("password"));
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (cooldown || submitting.current) return;
    // Password managers can fill the native fields without React change events.
    // Synchronize those values before Zod validation, never trim the password.
    const values = new FormData(event.currentTarget);
    for (const name of ["username", "password"] as const) {
      const value = values.get(name);
      if (typeof value === "string") form.setValue(name, value);
    }
    void form.handleSubmit(submit)(event);
  }
  return (
    <form onSubmit={handleSubmit} className={s.formStack} noValidate>
      {!reauth ? (
        <div className={s.profileChoices} aria-label="Демонстрационные профили">
          <Button
            size={32}
            disabled={form.formState.isSubmitting}
            onClick={() =>
              form.setValue("username", "client", { shouldValidate: true })
            }
          >
            Клиент
          </Button>
          <Button
            size={32}
            disabled={form.formState.isSubmitting}
            onClick={() =>
              form.setValue("username", "specialist", { shouldValidate: true })
            }
          >
            Специалист
          </Button>
        </div>
      ) : null}
      <Controller
        name="username"
        control={form.control}
        render={({ field, fieldState }) => (
          <Input
            {...field}
            onChange={(_, { value }) => field.onChange(value)}
            id={`${id}-username`}
            label="Логин"
            labelView="outer"
            block
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            disabled={form.formState.isSubmitting}
            aria-invalid={!!fieldState.error}
            aria-describedby={
              fieldState.error ? `${id}-username-error` : undefined
            }
            error={
              fieldState.error ? (
                <span id={`${id}-username-error`}>
                  {fieldState.error.message}
                </span>
              ) : undefined
            }
          />
        )}
      />
      <Controller
        name="password"
        control={form.control}
        render={({ field, fieldState }) => (
          <Input
            {...field}
            onChange={(_, { value }) => field.onChange(value)}
            id={`${id}-password`}
            label="Пароль"
            labelView="outer"
            block
            autoComplete="current-password"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            type={passwordVisible ? "text" : "password"}
            rightAddons={
              <Button
                type="button"
                size={32}
                view="text"
                aria-label={
                  passwordVisible ? "Скрыть пароль" : "Показать пароль"
                }
                aria-pressed={passwordVisible}
                disabled={form.formState.isSubmitting}
                onClick={() => setPasswordVisible((visible) => !visible)}
              >
                {passwordVisible ? "Скрыть" : "Показать"}
              </Button>
            }
            disabled={form.formState.isSubmitting}
            aria-invalid={!!fieldState.error}
            aria-describedby={
              fieldState.error ? `${id}-password-error` : undefined
            }
            error={
              fieldState.error ? (
                <span id={`${id}-password-error`}>
                  {fieldState.error.message}
                </span>
              ) : undefined
            }
          />
        )}
      />
      {error ? <ErrorNotice error={error} /> : null}
      <Button
        type="submit"
        view="accent"
        block
        loading={pending}
        disabled={form.formState.isSubmitting || cooldown > 0}
      >
        {reauth ? "Восстановить сессию" : "Войти в кабинет"}
      </Button>
      {!reauth ? (
        <p className={s.muted}>
          Используйте демо-профиль и пароль из настроек проекта. Роль и
          полномочия определяет сервер.
        </p>
      ) : null}
    </form>
  );
}

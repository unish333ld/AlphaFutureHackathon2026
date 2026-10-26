import { useEffect, useRef, useState } from "react";
import { useForm, Controller, type FieldPath } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useAuth } from "../app/auth";
import { useApplication, useCatalogs, useRefreshCredit } from "../app/queries";
import {
  api,
  type Application,
  type Product,
  type Revision,
} from "../shared/api/client";
import { ApiError } from "../shared/api/errors";
import {
  actionFor,
  cents,
  currentRevision,
  displayName,
  money,
  normalizeMoney,
  rate,
  reasons,
} from "../entities/credit";
import {
  Button,
  Checkbox,
  Choice,
  Empty,
  ErrorNotice,
  Facts,
  Input,
  Loading,
  Notice,
  Panel,
  Textarea,
  useRetryCooldown,
} from "../shared/ui/kit";
import { LinkButton, useUnsavedGuard } from "../shared/ui/navigation";
import { PageTitle } from "../shared/ui/PageTitle";
import { useAssistantForm } from "./AssistantFormContext";
import { CreditCost } from "./CreditDisclosure";
import s from "../app/layout.module.css";
import f from "./form.module.css";

const financialFields = [
  "monthly_revenue",
  "monthly_expenses",
  "monthly_debt_payments",
] as const;
const financialLabels = {
  monthly_revenue: "Месячная выручка",
  monthly_expenses: "Месячные расходы",
  monthly_debt_payments: "Месячные платежи по обязательствам",
};
export type FormValues = {
  company: string;
  product: string;
  amount: string;
  term_months: string;
  purpose: string;
  monthly_revenue: string;
  monthly_expenses: string;
  monthly_debt_payments: string;
};
export function formSchema(products: Product[]) {
  const financial = z
    .string()
    .refine(
      (v) => v.trim() === "" || normalizeMoney(v) !== null,
      "Введите неотрицательную сумму с точностью до копеек",
    );
  return z
    .object({
      company: z
        .string()
        .regex(
          /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
          "Выберите компанию",
        ),
      product: z
        .string()
        .regex(
          /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
          "Выберите продукт",
        ),
      amount: z
        .string()
        .refine(
          (v) => normalizeMoney(v) !== null && cents(v) > 0n,
          "Введите положительную сумму с точностью до копеек",
        ),
      term_months: z.string().regex(/^\d+$/, "Укажите целое число месяцев"),
      purpose: z
        .string()
        .trim()
        .min(1, "Расскажите, для чего нужны деньги")
        .max(500, "Не более 500 символов"),
      monthly_revenue: financial,
      monthly_expenses: financial,
      monthly_debt_payments: financial,
    })
    .superRefine((data, ctx) => {
      const product = products.find((item) => item.id === data.product);
      if (!product) {
        ctx.addIssue({
          code: "custom",
          path: ["product"],
          message: "Выберите доступный продукт",
        });
        return;
      }
      if (
        normalizeMoney(data.amount) &&
        (cents(data.amount) < cents(product.min_amount) ||
          cents(data.amount) > cents(product.max_amount))
      )
        ctx.addIssue({
          code: "custom",
          path: ["amount"],
          message: `От ${money(product.min_amount)} до ${money(product.max_amount)}`,
        });
      const term = Number(data.term_months);
      if (
        !Number.isInteger(term) ||
        term < product.min_term_months ||
        term > product.max_term_months
      )
        ctx.addIssue({
          code: "custom",
          path: ["term_months"],
          message: `От ${product.min_term_months} до ${product.max_term_months} месяцев`,
        });
    });
}
export function revisionPayload(values: FormValues) {
  return {
    amount: normalizeMoney(values.amount)!,
    term_months: Number(values.term_months),
    purpose: values.purpose.trim(),
    monthly_revenue: values.monthly_revenue.trim()
      ? normalizeMoney(values.monthly_revenue)!
      : null,
    monthly_expenses: values.monthly_expenses.trim()
      ? normalizeMoney(values.monthly_expenses)!
      : null,
    monthly_debt_payments: values.monthly_debt_payments.trim()
      ? normalizeMoney(values.monthly_debt_payments)!
      : null,
  };
}
function fromRevision(app: Application, revision: Revision): FormValues {
  return {
    company: app.company,
    product: app.product,
    amount: revision.amount,
    term_months: String(revision.term_months),
    purpose: revision.purpose,
    monthly_revenue: revision.monthly_revenue ?? "",
    monthly_expenses: revision.monthly_expenses ?? "",
    monthly_debt_payments: revision.monthly_debt_payments ?? "",
  };
}

export default function ApplicationFormRoute() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const app = useApplication(id ?? "00000000-0000-0000-0000-000000000000");
  // For a new application no object lookup is needed; see separate routes below.
  return id ? (
    app.isPending ? (
      <Loading />
    ) : !app.data ? (
      <ErrorNotice
        error={app.error}
        retry={() => {
          void app.refetch();
        }}
      />
    ) : (
      <>
        {app.isError ? (
          <ErrorNotice
            error={app.error}
            retry={() => {
              void app.refetch();
            }}
          />
        ) : null}
        <ApplicationForm
          key={`${id}:${params.get("mode") ?? "draft"}`}
          initial={app.data}
          mode={
            params.get("mode") === "answer"
              ? "answer"
              : params.get("mode") === "revise"
                ? "revise"
                : "draft"
          }
        />
      </>
    )
  ) : (
    <ApplicationForm mode="new" />
  );
}
export function NewApplicationPage() {
  return <ApplicationForm mode="new" />;
}

function ApplicationForm({
  initial,
  mode,
}: {
  initial?: Application;
  mode: "new" | "draft" | "answer" | "revise";
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const assistantBridge = useAssistantForm();
  const assistantDraft = useRef(
    mode === "new" ? assistantBridge.transfer.current : null,
  ).current;
  const [params] = useSearchParams();
  const refresh = useRefreshCredit();
  const { companies, products } = useCatalogs();
  const revision = initial ? currentRevision(initial) : null;
  const [base, setBase] = useState(initial);
  const [step, setStep] = useState<"parameters" | "review">("parameters");
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [step]);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const cooldown = useRetryCooldown(error);
  const [conflict, setConflict] = useState<Application | null>(null);
  const [uncertainCreate, setUncertainCreate] = useState(false);
  const [calcFor, setCalcFor] = useState("");
  const initialized = useRef(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema(products.data ?? [])),
    defaultValues:
      initial && revision
        ? fromRevision(initial, revision)
        : {
            company: assistantDraft?.company ?? params.get("company") ?? "",
            product: assistantDraft?.product ?? params.get("product") ?? "",
            amount: assistantDraft?.amount ?? "1000000.00",
            term_months: String(assistantDraft?.term_months ?? 24),
            purpose: assistantDraft?.purpose ?? "",
            monthly_revenue: "",
            monthly_expenses: "",
            monthly_debt_payments: "",
          },
  });
  const values = form.watch();
  useEffect(() => {
    assistantBridge.setSelection((previous) =>
      previous?.company === values.company &&
      previous.product === values.product
        ? previous
        : { company: values.company, product: values.product },
    );
  }, [assistantBridge.setSelection, values.company, values.product]);
  useEffect(
    () => () => assistantBridge.setSelection(null),
    [assistantBridge.setSelection],
  );
  useEffect(() => {
    assistantBridge.transfer.current = null;
    const snapshot = () => ({
      ...form.getValues(),
      fingerprint: JSON.stringify([
        form.getValues(),
        base?.id,
        base?.lock_version,
        mode,
      ]),
    });
    const adapter = {
      snapshot,
      apply: (
        draft: import("./assistantDraft").AssistantDraft,
        expected: string,
      ) => {
        const current = snapshot();
        if (
          expected !== current.fingerprint ||
          draft.company !== current.company ||
          draft.product !== current.product
        )
          return false;
        form.setValue("amount", draft.amount, {
          shouldDirty: true,
          shouldValidate: true,
        });
        form.setValue("term_months", String(draft.term_months), {
          shouldDirty: true,
          shouldValidate: true,
        });
        form.setValue("purpose", draft.purpose, {
          shouldDirty: true,
          shouldValidate: true,
        });
        setStep("parameters");
        setConfirmed(false);
        return true;
      },
    };
    assistantBridge.form.current = adapter;
    return () => {
      if (assistantBridge.form.current === adapter)
        assistantBridge.form.current = null;
    };
  }, [assistantBridge, form, base?.id, base?.lock_version, mode]);
  const product = products.data?.find((item) => item.id === values.product);
  const company = companies.data?.find((item) => item.id === values.company);
  const calculate = useMutation({ mutationFn: api.calculator, retry: false });
  const membership = user?.memberships.find(
    (item) => item.company === values.company && item.active,
  );
  useEffect(() => {
    if (initialized.current || !companies.data || !products.data) return;
    initialized.current = true;
    if (!initial) {
      const selected =
        products.data.find((p) => p.id === assistantDraft?.product) ??
        products.data.find((p) => p.id === params.get("product")) ??
        products.data[0];
      const selectedCompany =
        companies.data.find((c) => c.id === assistantDraft?.company) ??
        companies.data.find((c) => c.id === params.get("company")) ??
        companies.data[0];
      const current = form.getValues();
      form.reset({
        ...current,
        company: selectedCompany?.id ?? "",
        product: selected?.id ?? "",
        purpose:
          assistantDraft && selected?.id === assistantDraft.product
            ? assistantDraft.purpose
            : selected?.code === "equipment"
              ? "Приобретение оборудования"
              : "Пополнение оборотных средств",
      });
    }
  }, [companies.data, products.data, initial, form, params, assistantDraft]);
  const guard = useUnsavedGuard(form.formState.isDirty);
  const field = (name: FieldPath<FormValues>, label: string, hint?: string) => (
    <Controller
      name={name}
      control={form.control}
      render={({ field: input, fieldState }) => (
        <Input
          {...input}
          value={input.value}
          onChange={(event) => input.onChange(event.target.value)}
          label={label}
          labelView="outer"
          inputMode={name === "term_months" ? "numeric" : "decimal"}
          block
          error={fieldState.error?.message}
          hint={hint}
        />
      )}
    />
  );
  const snapshotKey = `${values.amount}:${values.term_months}:${values.product}:${product?.rules_version}:${product?.annual_rate}`;
  function calculator() {
    if (
      !product ||
      !normalizeMoney(values.amount) ||
      !/^\d+$/.test(values.term_months)
    )
      return;
    const amount = normalizeMoney(values.amount)!;
    setCalcFor(snapshotKey);
    calculate.mutate({
      amount,
      term_months: Number(values.term_months),
      product: product.id,
    });
  }
  const mutation = useMutation({
    retry: false,
    mutationFn: async ({
      values: input,
      send,
    }: {
      values: FormValues;
      send: boolean;
    }) => {
      setError(null);
      let saved = base;
      try {
        const payload = revisionPayload(input);
        if (mode === "answer" || mode === "revise") {
          if (!saved) throw new Error("Missing application");
          const action = actionFor(
            saved,
            mode === "answer" ? "provide_information" : "revise",
          );
          if (!action?.allowed) throw new Error("Action unavailable");
          const result = await api.revise(action, {
            ...payload,
            lock_version: saved.lock_version,
          });
          await refresh(result);
          guard.allowNavigation();
          form.reset(input);
          navigate(`/app/loans/${result.id}/submitted`, { replace: true });
          return;
        }
        if (saved) {
          if (!actionFor(saved, "update_draft")?.allowed)
            throw new Error("Draft edit unavailable");
          saved = await api.patch(saved.id, {
            ...payload,
            lock_version: saved.lock_version,
          });
        } else
          saved = await api.create({
            ...payload,
            company: input.company,
            product: input.product,
          });
        setBase(saved);
        if (send) {
          const submit = actionFor(saved, "submit");
          if (!submit?.allowed)
            throw new ApiError(403, {
              detail:
                reasons[submit?.reason_code ?? ""] ??
                "Недостаточно полномочий для отправки.",
            });
          const response = await api.action(submit, saved.lock_version);
          if (!("revisions" in response))
            throw new Error("Unexpected response");
          saved = response;
        }
        await refresh();
        form.reset(input);
        guard.allowNavigation();
        navigate(`/app/loans/${saved.id}${send ? "/submitted" : ""}`, {
          replace: true,
        });
      } catch (cause) {
        setError(cause);
        if (cause instanceof ApiError) {
          for (const [key, message] of Object.entries(cause.normalized.fields))
            if (key in form.getValues())
              form.setError(key as FieldPath<FormValues>, {
                type: "server",
                message,
              });
          if (Object.keys(cause.normalized.fields).length)
            setStep("parameters");
          if (cause.status === 409 && saved) {
            await refresh();
            const latest = await api
              .application(saved.id)
              .catch(() => undefined);
            if (latest) setConflict(latest);
            setConfirmed(false);
          } else if (cause.uncertain) {
            if (saved) {
              const latest = await api
                .application(saved.id)
                .catch(() => undefined);
              if (
                latest &&
                currentRevision(latest)?.submitted_at &&
                latest.status !== "draft"
              ) {
                guard.allowNavigation();
                navigate(`/app/loans/${latest.id}`, { replace: true });
                return;
              }
              if (latest) setBase(latest);
            } else setUncertainCreate(true);
          }
        }
        throw cause;
      }
    },
  });
  const pending = mutation.isPending || cooldown > 0;
  const expected =
    mode === "answer"
      ? "provide_information"
      : mode === "revise"
        ? "revise"
        : "update_draft";
  const allowed = !base || !!actionFor(base, expected)?.allowed;
  if (companies.isPending || products.isPending) return <Loading />;
  if (companies.isError || products.isError)
    return (
      <ErrorNotice
        error={companies.error ?? products.error}
        retry={() => {
          void companies.refetch();
          void products.refetch();
        }}
      />
    );
  if (initial && !revision)
    return (
      <Notice tone="error">
        Нет актуальной ревизии.{" "}
        <Link to={`/app/loans/${initial.id}`}>Вернуться к карточке</Link>
      </Notice>
    );
  if (!companies.data?.length || !products.data?.length)
    return (
      <Panel>
        <Empty
          title="Нет доступных компаний или продуктов"
          action={<LinkButton to="/app">На главную</LinkButton>}
        >
          Проверьте полномочия и доступность продукта.
        </Empty>
      </Panel>
    );
  const openRequests =
    revision?.information_requests.filter((item) => !item.response_revision) ??
    [];
  return (
    <>
      <div className={s.breadcrumb}>
        <Link to="/app/loans">Заявки и кредиты</Link>
        <span>/</span>
        <span>{initial?.number ?? "Новая заявка"}</span>
      </div>
      <ol className={f.steps} aria-label="Шаги заявки">
        <li aria-current={step === "parameters" ? "step" : undefined}>
          <span>1</span>Параметры и показатели
        </li>
        <li aria-current={step === "review" ? "step" : undefined}>
          <span>2</span>Проверка
        </li>
        <li>
          <span>3</span>Отправка
        </li>
      </ol>
      <PageTitle
        title={
          mode === "answer"
            ? "Проверьте данные заявки"
            : mode === "revise"
              ? "Пересмотрите параметры"
              : step === "review"
                ? "Проверьте заявку"
                : "Для чего нужны деньги?"
        }
        subtitle={
          step === "review"
            ? "Проверьте все сведения. Отправка заявки не означает одобрение кредита."
            : "Выберите продукт и расскажите о задаче бизнеса."
        }
      />
      {error ? (
        <div style={{ marginBottom: 22 }}>
          <ErrorNotice error={error} />
        </div>
      ) : null}
      {conflict ? (
        <div className={s.stack} style={{ marginBottom: 22 }}>
          <Notice tone="warning" title="Серверные данные изменились">
            Ваш ввод сохранён. Ниже — текущие данные сервера. Сравните их с
            формой перед продолжением.
          </Notice>
          <Panel title={`Текущая версия ${conflict.lock_version}`}>
            <Facts
              rows={[
                {
                  label: "Сумма на сервере",
                  value: money(currentRevision(conflict)?.amount),
                },
                {
                  label: "Срок на сервере",
                  value: `${currentRevision(conflict)?.term_months ?? "—"} мес.`,
                },
                {
                  label: "Назначение",
                  value: currentRevision(conflict)?.purpose ?? "Нет данных",
                },
              ]}
            />
            <div className={s.actions}>
              <Button
                disabled={!actionFor(conflict, expected)?.allowed}
                onClick={() => {
                  setBase(conflict);
                  setConflict(null);
                  setError(null);
                  setConfirmed(false);
                  setStep("review");
                }}
              >
                Сведения проверены — использовать новую версию
              </Button>
              <LinkButton to={`/app/loans/${conflict.id}`}>
                Открыть карточку
              </LinkButton>
            </div>
          </Panel>
        </div>
      ) : null}
      {uncertainCreate ? (
        <Notice tone="warning" title="Сохранение не подтверждено">
          Черновик мог быть создан. Сначала проверьте список заявок; повторное
          создание не запускается автоматически.{" "}
          <LinkButton to="/app/loans">Проверить заявки</LinkButton>
          <Button
            onClick={() => {
              setUncertainCreate(false);
              setError(null);
            }}
          >
            Список проверен — продолжить
          </Button>
        </Notice>
      ) : null}
      {!allowed ? (
        <Notice tone="warning">
          {reasons[actionFor(base!, expected)?.reason_code ?? ""] ??
            "Действие больше недоступно. Откройте карточку и проверьте состояние."}
        </Notice>
      ) : null}
      {mode === "answer" && openRequests.length ? (
        <Panel title="Запрос банка">
          {openRequests.map((item) => (
            <p key={item.id}>{item.question}</p>
          ))}
        </Panel>
      ) : null}
      <form
        className={s.stack}
        noValidate
        onSubmit={form.handleSubmit((input) => {
          if (step === "parameters") {
            setStep("review");
            setConfirmed(false);
          } else if (confirmed && !pending)
            mutation.mutate({ values: input, send: true });
        })}
      >
        <div className={s.columns}>
          <div className={s.stack}>
            {step === "parameters" ? (
              <>
                <Panel title="Параметры кредита">
                  <div className={s.formStack}>
                    <Controller
                      name="company"
                      control={form.control}
                      render={({ field: input, fieldState }) => (
                        <Choice
                          label="Компания"
                          value={input.value}
                          onChange={input.onChange}
                          options={companies.data.map((item) => ({
                            key: item.id,
                            content: displayName(item.name),
                          }))}
                          disabled={!!base}
                          error={fieldState.error?.message}
                        />
                      )}
                    />
                    <Controller
                      name="product"
                      control={form.control}
                      render={({ field: input, fieldState }) => (
                        <Choice
                          label="Кредитный продукт"
                          value={input.value}
                          onChange={input.onChange}
                          options={products.data.map((item) => ({
                            key: item.id,
                            content: displayName(item.name),
                          }))}
                          disabled={!!base}
                          error={fieldState.error?.message}
                        />
                      )}
                    />
                    {field(
                      "amount",
                      "Сумма, ₽",
                      product
                        ? `${money(product.min_amount)} — ${money(product.max_amount)}`
                        : undefined,
                    )}
                    {field(
                      "term_months",
                      "Срок, месяцев",
                      product
                        ? `${product.min_term_months}–${product.max_term_months} мес.`
                        : undefined,
                    )}
                    <Controller
                      name="purpose"
                      control={form.control}
                      render={({ field: input, fieldState }) => (
                        <Textarea
                          {...input}
                          id="application-purpose"
                          aria-label="Цель кредита"
                          aria-invalid={!!fieldState.error}
                          label="Цель кредита"
                          labelView="outer"
                          block
                          minRows={3}
                          maxLength={500}
                          error={fieldState.error?.message}
                        />
                      )}
                    />
                  </div>
                </Panel>
                <Panel title="Финансовые показатели">
                  <p className={s.muted}>
                    Укажите суммы за один месяц. Если показатель пока
                    неизвестен, оставьте поле пустым. Специалист попросит
                    проверить данные. Для отсутствующих обязательств укажите 0.
                  </p>
                  <p>
                    Указано{" "}
                    {
                      financialFields.filter(
                        (name) => normalizeMoney(values[name]) !== null,
                      ).length
                    }{" "}
                    из 3 показателей. Заполненность не означает одобрение.
                  </p>
                  <ul
                    className={s.checkList}
                    aria-label="Что проверить перед отправкой"
                  >
                    {financialFields
                      .filter((name) => normalizeMoney(values[name]) === null)
                      .map((name) => (
                        <li key={name}>
                          <Button
                            size={40}
                            view="text"
                            onClick={() => form.setFocus(name)}
                          >
                            Проверить: {financialLabels[name]}
                          </Button>
                        </li>
                      ))}
                  </ul>
                  <p className={s.muted}>
                    Расходы включают операционные затраты и налоги. Платежи по
                    долгам указывайте отдельно за тот же месяц — они учитываются
                    один раз.
                  </p>
                  <div className={s.formStack}>
                    {financialFields.map((name) => (
                      <div key={name}>
                        {field(name, `${financialLabels[name]}, ₽`)}
                      </div>
                    ))}
                  </div>
                </Panel>
              </>
            ) : (
              <>
                <Panel title="Данные компании">
                  <h3>{displayName(company?.name ?? initial?.company_name)}</h3>
                  <Facts
                    rows={[
                      { label: "ИНН", value: company?.inn ?? "Нет данных" },
                      {
                        label: "Представитель",
                        value: user?.first_name || user?.username,
                      },
                      {
                        label: "Право отправки",
                        value: membership?.can_submit ? "Есть" : "Нет",
                      },
                    ]}
                  />
                </Panel>
                <Panel title="Ваша заявка">
                  <Facts
                    rows={[
                      {
                        label: "Продукт",
                        value: product?.name ?? initial?.product_name,
                      },
                      {
                        label: "Сумма",
                        value: money(normalizeMoney(values.amount)),
                      },
                      { label: "Срок", value: `${values.term_months} мес.` },
                      { label: "Цель", value: values.purpose },
                      ...financialFields.map((name) => ({
                        label: financialLabels[name],
                        value: values[name].trim()
                          ? money(normalizeMoney(values[name]))
                          : "Пока не указано",
                      })),
                    ]}
                  />
                </Panel>
                <Checkbox
                  label="Подтверждаю, что проверил(а) параметры и сведения"
                  checked={confirmed}
                  onChange={(_, { checked }) => setConfirmed(checked)}
                  block
                />
                {financialFields.some((name) => !values[name].trim()) ? (
                  <Notice tone="warning">
                    Часть финансовых данных не указана. Банк сможет запросить их
                    новой ревизией.
                  </Notice>
                ) : null}
              </>
            )}
          </div>
          <aside className={s.stack}>
            <Panel title="Данные компании">
              <h3>
                {displayName(company?.name ?? initial?.company_name) ||
                  "Выберите компанию"}
              </h3>
              <p className={s.muted}>
                {company
                  ? `ИНН ${company.inn}`
                  : "Сведения поступают из доступного вам профиля."}
              </p>
              <p className={s.muted}>
                Компания и продукт сохранённой заявки не меняются. Изменённые
                финансовые сведения после отправки проходят повторную проверку.
              </p>
            </Panel>
            <Panel title="Предварительный платёж">
              <p className={s.muted}>
                {product
                  ? `Предварительная ставка — ${rate(product.annual_rate)}`
                  : "Выберите продукт"}
              </p>
              {calculate.data &&
              calcFor === snapshotKey &&
              calculate.data.catalog_version === product?.rules_version ? (
                <>
                  <div className={s.bigAmount}>
                    {money(calculate.data.monthly_payment)}
                  </div>
                  <p className={s.muted}>Предварительный платёж в месяц.</p>
                  <CreditCost value={calculate.data.cost_breakdown} />
                </>
              ) : (
                <p className={s.muted}>
                  Рассчитайте платёж по выбранным сумме и сроку. Это не
                  кредитное предложение.
                </p>
              )}
              {calculate.isError ? (
                <ErrorNotice error={calculate.error} />
              ) : null}
              <Button
                size={40}
                onClick={calculator}
                disabled={
                  !product ||
                  calculate.isPending ||
                  !normalizeMoney(values.amount)
                }
                loading={calculate.isPending}
              >
                Рассчитать платёж
              </Button>
            </Panel>
            <Panel title="Что будет дальше">
              <ol className={s.checkList}>
                {[
                  "Банк проверит отправленные сведения",
                  "Вы получите решение и условия",
                  "Принятие, условная подпись и моделируемая выдача",
                ].map((label, i) => (
                  <li key={label}>
                    <span className={s.stepDot}>{i + 1}</span>
                    <span>{label}</span>
                  </li>
                ))}
              </ol>
              <p className={s.muted}>Отправка заявки не означает одобрение.</p>
            </Panel>
          </aside>
        </div>
        <div className={f.formFooter}>
          {step === "review" ? (
            <Button onClick={() => setStep("parameters")} disabled={pending}>
              Назад к параметрам
            </Button>
          ) : (
            <LinkButton
              to={initial ? `/app/loans/${initial.id}` : "/app/loans"}
            >
              Отмена
            </LinkButton>
          )}
          <div className={s.inline}>
            {mode === "new" || mode === "draft" ? (
              <Button
                loading={pending}
                disabled={pending || !!conflict || uncertainCreate || !allowed}
                onClick={() => {
                  void form.handleSubmit((input) =>
                    mutation.mutate({ values: input, send: false }),
                  )();
                }}
              >
                Сохранить черновик
              </Button>
            ) : null}
            <Button
              type="submit"
              view="accent"
              loading={pending}
              disabled={
                pending ||
                !!conflict ||
                uncertainCreate ||
                !allowed ||
                (step === "review" && (!confirmed || !membership?.can_submit))
              }
            >
              {step === "parameters"
                ? "Проверить заявку"
                : mode === "answer"
                  ? "Отправить проверенные данные"
                  : mode === "revise"
                    ? "Отправить изменения"
                    : "Отправить заявку"}
            </Button>
          </div>
        </div>
      </form>
      {guard.dialog}
    </>
  );
}

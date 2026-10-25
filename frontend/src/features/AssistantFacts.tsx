import { Button } from "../shared/ui/kit";
import { money as formatMoney, statuses } from "../entities/credit";
import type { Status } from "../shared/api/client";
import { parseAssistantDraft, type AssistantDraft } from "./assistantDraft";
import s from "./assistant.module.css";

const record = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
const string = (value: unknown) =>
  typeof value === "string" ? value : undefined;
const money = (value: unknown) =>
  typeof value === "string" && /^\d+\.\d{2}$/.test(value)
    ? formatMoney(value)
    : undefined;

function Fact({ value }: { value: unknown }) {
  const fact = record(value);
  const data = record(fact?.data);
  if (!data) return null;
  const source = string(fact?.source);
  if (data.error === "unknown_product_code")
    return (
      <div className={s.fact}>
        <strong>Продукт не найден</strong>
        <span>Выберите продукт из доступных в кабинете.</span>
        {Array.isArray(data.available_products) &&
        data.available_products.length ? (
          <small>
            Доступны:{" "}
            {data.available_products
              .slice(0, 4)
              .map((value) => string(record(value)?.name))
              .filter(Boolean)
              .join(", ")}
          </small>
        ) : null}
      </div>
    );
  if (source === "get_company_profile")
    return (
      <div className={s.fact}>
        <strong>Компания</strong>
        <span>{string(data.name) ?? "Данные компании"}</span>
      </div>
    );
  if (source === "list_credit_products") {
    const products = Array.isArray(data.products) ? data.products : [];
    return (
      <div className={s.fact}>
        <strong>Демонстрационные продукты</strong>
        {products.slice(0, 4).map((value, index) => {
          const product = record(value);
          return <span key={index}>{string(product?.name) ?? "Продукт"}</span>;
        })}
      </div>
    );
  }
  if (source === "calculate_payment")
    return (
      <div className={s.fact}>
        <strong>Предварительный демо-расчёт</strong>
        <span>Сумма: {money(data.amount) ?? "—"}</span>
        <span>Ежемесячный платёж: {money(data.monthly_payment) ?? "—"}</span>
        <small>Расчёт не является кредитным решением.</small>
      </div>
    );
  if (source === "get_application_status") {
    const status = string(data.status);
    const label =
      status && status in statuses ? statuses[status as Status] : "Не выбрана";
    const decision = record(data.decision);
    return (
      <div className={s.fact}>
        <strong>Сохранённые данные заявки</strong>
        <span>Статус: {label}</span>
        {string(decision?.explanation) ? (
          <span>{string(decision?.explanation)}</span>
        ) : null}
      </div>
    );
  }
  return null;
}

export function AssistantFacts({
  facts,
  suggestedDraft,
  company,
  onDraft,
}: {
  facts: unknown[];
  suggestedDraft: unknown;
  company: string;
  onDraft: (draft: AssistantDraft) => void;
}) {
  const draft = parseAssistantDraft(suggestedDraft, company);
  return (
    <>
      {facts.map((fact, index) => (
        <Fact key={index} value={fact} />
      ))}
      {draft ? (
        <div className={s.fact}>
          <strong>Предложение черновика</strong>
          <span>Сумма: {money(draft.amount)}</span>
          <span>Срок: {draft.term_months} мес.</span>
          <span>Цель: {draft.purpose}</span>
          <small>Заявка ещё не создана. Проверьте поля в форме.</small>
          <Button size={40} onClick={() => onDraft(draft)}>
            Проверить в заявке
          </Button>
        </div>
      ) : null}
    </>
  );
}

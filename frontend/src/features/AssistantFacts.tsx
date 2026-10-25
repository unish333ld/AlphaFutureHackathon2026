import { Link } from "react-router-dom";
import { Button } from "../shared/ui/kit";
import { money as formatMoney, statuses, nextSteps } from "../entities/credit";
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

function Fact({
  value,
  onProduct,
}: {
  value: unknown;
  onProduct: (name: string) => void;
}) {
  const fact = record(value);
  const data = record(fact?.data);
  if (!data) return null;
  const source = string(fact?.source);
  if (data.error === "unknown_product_code")
    return (
      <div className={s.fact}>
        <strong>Выберите доступный продукт</strong>
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
          const name = string(product?.name);
          return name ? (
            <button type="button" key={index} onClick={() => onProduct(name)}>
              {name}
            </button>
          ) : null;
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
        <span>
          Срок: {typeof data.term_months === "number" ? data.term_months : "—"}{" "}
          мес.
        </span>
        <span>
          Демо-ставка: {string(data.demo_annual_rate) ?? "—"}% годовых
        </span>
        <small>Расчёт не является кредитным решением.</small>
      </div>
    );
  if (source === "get_application_status") {
    const status = string(data.status);
    const label =
      status && status in statuses ? statuses[status as Status] : "Не выбрана";
    const decision = record(data.decision);
    const offer = record(data.offer);
    return (
      <div className={s.fact}>
        <strong>Сохранённые данные заявки</strong>
        <span>Статус: {label}</span>
        {status && status in nextSteps ? (
          <span>{nextSteps[status as Status]}</span>
        ) : null}
        <small>
          Источник: сохранённая заявка {string(data.number)}. Версия:{" "}
          {typeof data.lock_version === "number" ? data.lock_version : "—"}.
          Перед действием откройте актуальную карточку.
        </small>
        {string(decision?.explanation) ? (
          <span>{string(decision?.explanation)}</span>
        ) : null}
        {offer ? (
          <>
            <span>
              Предложение: {money(offer.amount) ?? "—"},{" "}
              {typeof offer.term_months === "number" ? offer.term_months : "—"}{" "}
              мес.
            </span>
            <span>Ставка: {string(offer.annual_rate) ?? "—"}% годовых</span>
            <span>Платёж: {money(offer.monthly_payment) ?? "—"}</span>
          </>
        ) : null}
        {typeof data.application_id === "string" &&
        /^[0-9a-f-]{36}$/i.test(data.application_id) ? (
          <Link to={`/app/loans/${data.application_id}`}>
            Открыть карточку и доступные действия
          </Link>
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
  onProduct,
}: {
  facts: unknown[];
  suggestedDraft: unknown;
  company: string;
  onDraft: (draft: AssistantDraft) => void;
  onProduct: (name: string) => void;
}) {
  const draft = parseAssistantDraft(suggestedDraft, company);
  return (
    <>
      {facts.map((fact, index) => (
        <Fact key={index} value={fact} onProduct={onProduct} />
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

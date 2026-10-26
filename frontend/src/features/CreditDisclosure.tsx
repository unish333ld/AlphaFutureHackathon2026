import type { Product, Schema } from "../shared/api/client";
import { money, rate } from "../entities/credit";
import { Facts, Notice, Panel } from "../shared/ui/kit";
import s from "../app/layout.module.css";

export function CreditCost({ value }: { value: Schema["CostBreakdown"] }) {
  return (
    <section aria-label="Стоимость кредита" className={s.stack}>
      <Facts
        rows={[
          {
            label: "К зачислению на счёт",
            value: money(value.net_disbursement),
          },
          {
            label: "Проценты за весь срок",
            value: money(value.interest_total),
          },
          { label: "Всего к возврату", value: money(value.total_repayment) },
          {
            label: "Расходы сверх суммы кредита",
            value: money(value.total_cost),
          },
        ]}
      />
      <details>
        <summary className={s.link}>Разбивка расходов и платежей</summary>
        <Facts
          rows={[
            { label: "Основной долг", value: money(value.principal) },
            {
              label: "Комиссии в учебной модели",
              value: money(value.fees_total),
            },
            {
              label: "Допуслуги в учебной модели",
              value: money(value.services_total),
            },
            { label: "Первый платёж", value: money(value.first_payment) },
            { label: "Максимальный платёж", value: money(value.max_payment) },
            { label: "Последний платёж", value: money(value.last_payment) },
          ]}
        />
      </details>
      {!value.is_complete ? (
        <Notice tone="warning">
          Стоимость неполная: известные платежи составляют{" "}
          {money(value.known_payments_total)}. Неизвестные расходы не приняты за
          ноль.
        </Notice>
      ) : null}
      <p className={s.muted}>{value.disclosure}</p>
    </section>
  );
}

export function OfferComparison({
  value,
}: {
  value: Schema["OfferComparison"];
}) {
  const rows = [
    ["Сумма", money(value.requested.amount), money(value.proposed.amount)],
    [
      "Срок",
      `${value.requested.term_months} мес.`,
      `${value.proposed.term_months} мес.`,
    ],
    [
      "Годовая ставка",
      rate(value.requested.annual_rate),
      rate(value.proposed.annual_rate),
    ],
    [
      "Платёж в месяц",
      money(value.requested.monthly_payment),
      money(value.proposed.monthly_payment),
    ],
    [
      "Всего к возврату",
      money(value.requested.cost_breakdown.total_repayment),
      money(value.proposed.cost_breakdown.total_repayment),
    ],
  ];
  return (
    <section aria-label="Сравнение условий">
      <h3>Запрашивали → предлагаем</h3>
      <div
        className={s.scrollArea}
        role="region"
        aria-label="Сравнение запроса и предложения"
        tabIndex={0}
      >
        <table className={s.comparisonTable}>
          <thead>
            <tr>
              <th scope="col">Параметр</th>
              <th scope="col">Запрашивали</th>
              <th scope="col">Предлагаем</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, requested, proposed]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                <td>{requested}</td>
                <td>
                  <strong>{proposed}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={s.muted}>
        Сравниваются ваш рассмотренный запрос и сохранённые условия предложения.{" "}
        {value.explanation}
      </p>
    </section>
  );
}

export function ProductReference({ product }: { product: Product }) {
  const reference = product.catalog_reference;
  if (!reference) return null;
  return (
    <Panel title="Откуда взяты условия">
      <p>Учебная ставка — {rate(product.annual_rate)} годовых.</p>
      <p className={s.muted}>
        Публичный ориентир: {money(reference.min_amount)}–
        {money(reference.max_amount)}, {reference.min_term_months}–
        {reference.max_term_months} месяцев. Ставка банка — от{" "}
        {rate(reference.advertised_rate_from)}.
      </p>
      <p className={s.muted}>{reference.rate_note}</p>
      <p>
        <a href={reference.source_url} target="_blank" rel="noreferrer">
          {reference.source_title}
        </a>
      </p>
      <p className={s.muted}>
        Проверено {reference.observed_at.split("-").reverse().join(".")} по
        поисковой копии официальной страницы. Дата вступления тарифа в силу не
        установлена.
      </p>
      <details>
        <summary>Ограничения демо</summary>
        <p className={s.muted}>{reference.limitations}</p>
        <p className={s.muted}>
          На публичной странице указан срок деятельности от{" "}
          {reference.minimum_business_age_months} месяцев. В демо не
          подтверждается соответствие всем требованиям банка.
        </p>
      </details>
    </Panel>
  );
}

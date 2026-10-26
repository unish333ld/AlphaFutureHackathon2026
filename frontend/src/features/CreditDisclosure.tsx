import type { Schema } from "../shared/api/client";
import { money, rate } from "../entities/credit";
import { Facts, Notice } from "../shared/ui/kit";
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
              label: "Комиссии",
              value: money(value.fees_total),
            },
            {
              label: "Дополнительные услуги",
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
          Часть расходов пока неизвестна. Подтверждённые платежи:{" "}
          {money(value.known_payments_total)}.
        </Notice>
      ) : null}
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
      <h3>Сравнение условий</h3>
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
      {value.explanation ? (
        <p className={s.muted}>{value.explanation}</p>
      ) : null}
    </section>
  );
}

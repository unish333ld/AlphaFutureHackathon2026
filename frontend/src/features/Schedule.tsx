import type { Schema } from "../shared/api/client";
import { money } from "../entities/credit";
import s from "../app/layout.module.css";

export function Schedule({
  schedule,
}: {
  schedule: Schema["Offer"]["schedule"];
}) {
  return (
    <details>
      <summary className={s.link}>
        График платежей · {schedule.rows.length} мес.
      </summary>
      <p className={s.muted}>
        Демонстрационный аннуитет по номерам месяцев, без комиссий и календарных
        дат. Последняя строка корректирует округление.
      </p>
      <div
        className={s.scrollArea}
        tabIndex={0}
        role="region"
        aria-label="Таблица графика платежей"
      >
        <table style={{ minWidth: 520, fontSize: 13 }}>
          <thead>
            <tr>
              <th scope="col">Месяц</th>
              <th scope="col">Платёж</th>
              <th scope="col">Основной долг</th>
              <th scope="col">Проценты</th>
              <th scope="col">Остаток</th>
            </tr>
          </thead>
          <tbody>
            {schedule.rows.map((row) => (
              <tr key={row.month}>
                <th scope="row">{row.month}</th>
                <td>{money(row.payment)}</td>
                <td>{money(row.principal)}</td>
                <td>{money(row.interest)}</td>
                <td>{money(row.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

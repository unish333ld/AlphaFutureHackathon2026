import type { Application } from "../shared/api/client";
import { actionFor } from "../entities/credit";
import { LinkButton } from "../shared/ui/navigation";
import { Panel } from "../shared/ui/kit";
import s from "../app/layout.module.css";

const verificationText = {
  not_checked: "Проверка начнётся после отправки.",
  pending: "Проверка ещё не завершена.",
  technical_error: "Проверка прервалась. Её можно повторить.",
  needs_information: "Для проверки нужны недостающие сведения.",
  outdated: "После изменений нужна новая проверка.",
  checked: "Проверки завершены.",
};

export function ReadinessChecklist({
  app,
  staff,
}: {
  app: Application;
  staff: boolean;
}) {
  const value = app.readiness;
  const edit = actionFor(app, "update_draft")?.allowed
    ? ""
    : actionFor(app, "provide_information")?.allowed
      ? "?mode=answer"
      : actionFor(app, "revise")?.allowed
        ? "?mode=revise"
        : null;
  return (
    <Panel title="Заполненность финансовых данных">
      <p>
        Указано {value.items.filter((item) => item.state === "ready").length} из{" "}
        {value.items.length} показателей.
      </p>
      <ul className={s.checkList}>
        {value.items.map((item) => (
          <li key={item.field}>
            <div>
              <strong>
                {item.state === "ready"
                  ? "✓ Указано"
                  : item.state === "invalid"
                    ? "Некорректно"
                    : "Нужно проверить"}
                {": "}
                {item.label}
              </strong>
              {item.state !== "ready" ? (
                <p className={s.muted}>{item.message}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      <p className={s.muted}>{verificationText[value.verification_state]}</p>
      {!staff && !value.financial_data_complete && edit !== null ? (
        <LinkButton to={`/app/loans/${app.id}/edit${edit}`}>
          Проверить показатели
        </LinkButton>
      ) : null}
    </Panel>
  );
}

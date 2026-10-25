import { test, expect, actor, create, decide, post, showApp } from "./fixtures";
import { currentOffer } from "../../src/entities/credit";

test("permission denied, safe 429/503 handling and no automatic mutation retries", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  const accountant = await actor(browser, sessions, "accountant", baseURL!);
  try {
    let app = await decide(client.context, staff.context);
    app = await post(
      client.context,
      `offers/${currentOffer(app)!.id}/accept/`,
      { lock_version: app.lock_version },
    );
    await showApp(accountant.page, app);
    await expect(
      accountant.page.getByRole("button", {
        name: "Условно подписать",
        exact: true,
      }),
    ).toBeDisabled();
    await expect(
      accountant.page.getByText("У вас нет необходимых полномочий.", {
        exact: true,
      }),
    ).toBeVisible();
    const free = await create(client.context);
    await showApp(staff.page, free, true);
    let sent = 0;
    await staff.page.route("**/claim/", (route) => {
      sent++;
      return route.fulfill({
        status: 429,
        contentType: "application/json",
        headers: { "Retry-After": "60" },
        body: JSON.stringify({ detail: "Слишком много запросов." }),
      });
    });
    await staff.page
      .getByRole("button", { name: "Взять в работу", exact: true })
      .click();
    await expect(staff.page.getByRole("alert")).toContainText(
      "Повтор доступен через",
    );
    await expect(
      staff.page.getByRole("button", { name: "Взять в работу", exact: true }),
    ).toBeDisabled();
    expect(sent).toBe(1);
    await staff.page.unroute("**/claim/");
    await staff.page.reload();
    await showApp(staff.page, free, true);
    await staff.page.route("**/claim/", (route) => {
      sent++;
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal SQL secret must not leak" }),
      });
    });
    await staff.page
      .getByRole("button", { name: "Взять в работу", exact: true })
      .click();
    await expect(staff.page.getByRole("alert")).toContainText(
      "Сервис временно недоступен",
    );
    await expect(
      staff.page.getByText("Internal SQL secret must not leak", {
        exact: true,
      }),
    ).toHaveCount(0);
    expect(sent).toBe(2);
  } finally {
    await client.context.close();
    await staff.context.close();
    await accountant.context.close();
  }
});

test("expired session reauthentication retains same-user form input and uses rotated CSRF", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    await client.page.goto("/app/loans/new");
    await client.page
      .getByLabel("Цель кредита", { exact: true })
      .fill("Ввод до истечения сессии");
    await client.context.clearCookies();
    await client.page
      .getByRole("button", { name: "Сохранить черновик", exact: true })
      .click();
    const dialog = client.page.getByRole("dialog", {
      name: "Сессия требует входа",
    });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Логин", { exact: true }).fill("client");
    await dialog
      .getByLabel("Пароль", { exact: true })
      .fill(process.env.DEMO_PASSWORD!);
    await dialog
      .getByRole("button", { name: "Восстановить сессию", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    await expect(
      client.page.getByLabel("Цель кредита", { exact: true }),
    ).toHaveValue("Ввод до истечения сессии");
    const request = client.page.waitForRequest(
      (r) => r.url().endsWith("/api/v1/applications/") && r.method() === "POST",
    );
    await client.page
      .getByRole("button", { name: "Сохранить черновик", exact: true })
      .click();
    expect((await request).headers()["x-csrftoken"]).toBeTruthy();
    await expect(client.page).toHaveURL(/\/app\/loans\/[0-9a-f-]{36}$/);
  } finally {
    await client.context.close();
  }
});

test("field errors and unsaved navigation confirmation remain accessible", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    await client.page.goto("/app/loans/new");
    await client.page.getByLabel("Сумма, ₽", { exact: true }).fill("1.001");
    await client.page
      .getByRole("button", { name: "Проверить заявку", exact: true })
      .click();
    await expect(
      client.page.getByText(
        "Введите положительную сумму с точностью до копеек",
        { exact: true },
      ),
    ).toBeVisible();
    await client.page
      .getByRole("link", { name: "Отмена", exact: true })
      .click();
    const dialog = client.page.getByRole("dialog", {
      name: "Выйти без сохранения?",
    });
    await expect(dialog).toBeVisible();
    await dialog
      .getByRole("button", { name: "Вернуться к форме", exact: true })
      .click();
    await expect(
      client.page.getByLabel("Сумма, ₽", { exact: true }),
    ).toHaveValue("1.001");
    await client.page
      .getByRole("link", { name: "Отмена", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: "Выйти без сохранения", exact: true })
      .click();
    await expect(client.page).toHaveURL(/\/app\/loans$/);
  } finally {
    await client.context.close();
  }
});

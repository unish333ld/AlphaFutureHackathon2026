import { test, expect, actor, post, create, showApp } from "./fixtures";

test("background read failure retains unsaved draft and recovers without replacing input", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const app = await post(client.context, "applications/", {
      company: "00000000-0000-0000-0000-000000000001",
      product: "00000000-0000-0000-0000-000000000065",
      amount: "1000000.00",
      term_months: 24,
      purpose: "QA background refetch",
    });
    await client.page.goto(`/app/loans/${app.id}/edit`);
    const purpose = client.page.getByLabel("Цель кредита", { exact: true });
    await purpose.fill("Не потерять введённые сведения");
    let failReads = true;
    await client.page.route(
      `**/api/v1/applications/${app.id}/`,
      async (route) => {
        if (failReads) {
          await route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Сервис временно недоступен" }),
          });
        } else await route.continue();
      },
    );
    await client.page.clock.install();
    await client.page.clock.fastForward(21000);
    const response = client.page.waitForResponse(
      (r) => r.url().endsWith(`/applications/${app.id}/`) && r.status() === 503,
    );
    await client.page.evaluate(() =>
      window.dispatchEvent(new Event("visibilitychange")),
    );
    await response;
    await client.page.clock.runFor(2000);
    await expect(client.page.getByRole("alert")).toBeVisible();
    await expect(purpose).toHaveValue("Не потерять введённые сведения");
    failReads = false;
    await client.page
      .getByRole("button", { name: "Обновить данные", exact: true })
      .click();
    await expect(client.page.getByRole("alert")).toHaveCount(0);
    await expect(purpose).toHaveValue("Не потерять введённые сведения");
  } finally {
    await client.context.close();
  }
});

test("failed fresh read cannot authorize a decision from cached application data", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    let app = await create(client.context);
    app = await post(staff.context, `staff/applications/${app.id}/claim/`, {
      lock_version: app.lock_version,
    });
    await showApp(staff.page, app, true);
    let failReads = true;
    let decisions = 0;
    staff.page.on("request", (request) => {
      if (request.method() === "POST" && request.url().endsWith("/decide/"))
        decisions++;
    });
    await staff.page.route(
      `**/api/v1/staff/applications/${app.id}/`,
      async (route) => {
        if (failReads)
          await route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Сервис временно недоступен" }),
          });
        else await route.continue();
      },
    );
    await staff.page
      .getByRole("button", { name: "Принять решение по правилам", exact: true })
      .click();
    await expect(staff.page.getByRole("alert").first()).toBeVisible();
    await expect(staff.page.getByRole("dialog")).toHaveCount(0);
    await expect(
      staff.page.getByRole("button", {
        name: "Принять решение по правилам",
        exact: true,
      }),
    ).toBeEnabled();
    expect(decisions).toBe(0);
    failReads = false;
    await staff.page
      .getByRole("button", { name: "Обновить карточку", exact: true })
      .click();
    await staff.page
      .getByRole("button", { name: "Принять решение по правилам", exact: true })
      .click();
    await expect(staff.page.getByRole("dialog")).toBeVisible();
    expect(decisions).toBe(0);
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("background card failure does not erase the specialist clarification question", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    let app = await create(client.context);
    app = await post(staff.context, `staff/applications/${app.id}/claim/`, {
      lock_version: app.lock_version,
    });
    await showApp(staff.page, app, true);
    await staff.page
      .getByRole("button", { name: "Запросить уточнение", exact: true })
      .click();
    const question = staff.page.getByRole("dialog").getByRole("textbox");
    await question.fill("Уточните назначение финансирования");
    await staff.page.route(`**/api/v1/staff/applications/${app.id}/`, (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Сервис временно недоступен" }),
      }),
    );
    await staff.page.clock.install();
    await staff.page.clock.fastForward(21000);
    const response = staff.page.waitForResponse(
      (r) => r.url().endsWith(`/applications/${app.id}/`) && r.status() === 503,
    );
    await staff.page.evaluate(() =>
      window.dispatchEvent(new Event("visibilitychange")),
    );
    await response;
    await staff.page.clock.runFor(2000);
    await expect(staff.page.getByRole("dialog")).toBeVisible();
    await expect(question).toHaveValue("Уточните назначение финансирования");
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

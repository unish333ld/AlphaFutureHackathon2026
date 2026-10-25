import AxeBuilder from "@axe-core/playwright";
import {
  test,
  expect,
  actor,
  create,
  decide,
  getApp,
  post,
  signed,
  showApp,
  uiAction,
} from "./fixtures";
import { currentOffer, currentRevision } from "../../src/entities/credit";

test("real UI: create → claim → clarification revision → server decision → acceptance → signature → issuance", async ({
  browser,
  sessions,
  baseURL,
}, testInfo) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    await client.page.goto(
      "/app/loans/new?company=00000000-0000-0000-0000-000000000001",
    );
    await expect(
      client.page.getByRole("listbox", {
        name: "Кредитный продукт",
        exact: true,
      }),
    ).toBeVisible();
    await client.page
      .getByLabel("Сумма, ₽", { exact: true })
      .fill("1000000,01");
    await client.page
      .getByLabel("Месячная выручка, ₽", { exact: true })
      .fill("1500000");
    await client.page
      .getByLabel("Месячные расходы, ₽", { exact: true })
      .fill("900000");
    await client.page
      .getByLabel("Месячные платежи по обязательствам, ₽", { exact: true })
      .fill("50000");
    await client.page
      .getByRole("button", { name: "Проверить заявку", exact: true })
      .click();
    await client.page
      .getByLabel("Подтверждаю, что проверил(а) параметры и сведения")
      .press("Space");
    await client.page
      .getByRole("button", { name: "Отправить заявку", exact: true })
      .click();
    await expect(
      client.page.getByRole("heading", {
        name: /Заявка AC-.* отправлена/,
        exact: true,
      }),
    ).toBeVisible();
    const id = client.page.url().match(/loans\/([^/]+)\/submitted/)![1]!;
    let app = await getApp(client.context, id);
    expect(currentRevision(app)?.amount).toBe("1000000.01");
    await showApp(staff.page, app, true);
    await staff.page
      .getByRole("button", { name: "Взять в работу", exact: true })
      .click();
    await expect(
      staff.page.getByRole("button", { name: "Освободить заявку" }),
    ).toBeVisible();
    await staff.page
      .getByRole("button", { name: "Запросить уточнение", exact: true })
      .click();
    await staff.page
      .getByLabel("Какие сведения нужны?", { exact: true })
      .fill("Подтвердите месячную выручку и платежи.");
    await staff.page
      .getByRole("dialog")
      .getByRole("button", { name: "Отправить запрос", exact: true })
      .click();
    await expect(staff.page.getByRole("dialog")).toHaveCount(0);
    app = await getApp(client.context, id);
    expect(app.status).toBe("needs_info");
    await showApp(client.page, app);
    await client.page
      .getByRole("link", { name: "Ответить банку", exact: true })
      .click();
    await expect(
      client.page.getByText("Подтвердите месячную выручку и платежи.", {
        exact: true,
      }),
    ).toBeVisible();
    await client.page
      .getByLabel("Месячная выручка, ₽", { exact: true })
      .fill("1600000");
    await client.page
      .getByRole("button", { name: "Проверить заявку", exact: true })
      .click();
    await client.page
      .getByLabel("Подтверждаю, что проверил(а) параметры и сведения")
      .press("Space");
    await client.page
      .getByRole("button", { name: "Отправить уточнение", exact: true })
      .click();
    await expect(
      client.page.getByRole("heading", {
        name: /Заявка AC-.* отправлена/,
        exact: true,
      }),
    ).toBeVisible();
    app = await getApp(client.context, id);
    expect(currentRevision(app)?.revision_no).toBe(2);
    await showApp(staff.page, app, true);
    await uiAction(
      staff.page,
      "Принять решение по правилам",
      "Запустить правила",
    );
    await expect(
      staff.page.getByRole("heading", {
        name: "Запрошенные условия одобрены",
        exact: true,
      }),
    ).toBeVisible();
    app = await getApp(client.context, id);
    await showApp(client.page, app);
    await uiAction(client.page, "Принять предложение");
    await client.page
      .getByRole("button", { name: "Условно подписать", exact: true })
      .click();
    await expect(
      client.page
        .getByRole("dialog")
        .getByRole("button", { name: "Подтвердить", exact: true }),
    ).toBeDisabled();
    await client.page
      .getByLabel(/Подтверждаю условное подписание/)
      .press("Space");
    await client.page
      .getByRole("dialog")
      .getByRole("button", { name: "Подтвердить", exact: true })
      .click();
    await expect(client.page.getByRole("dialog")).toHaveCount(0);
    await expect(
      client.page.getByRole("button", {
        name: "Моделировать выдачу",
        exact: true,
      }),
    ).toHaveCount(0);
    app = await getApp(client.context, id);
    expect(app.status).toBe("signed");
    await showApp(staff.page, app, true);
    await uiAction(staff.page, "Моделировать выдачу");
    await expect(
      staff.page
        .getByRole("status")
        .filter({ hasText: "Выдача смоделирована" })
        .first(),
    ).toBeVisible();
    await staff.page.reload();
    await expect(
      staff.page.getByText("Выдача смоделирована", { exact: true }).first(),
    ).toBeVisible();
    app = await getApp(client.context, id);
    expect(app.status).toBe("issued");
    expect(currentOffer(app)?.agreement?.disbursement).toBeTruthy();
    await staff.page.screenshot({
      path: testInfo.outputPath("staff-issued.png"),
      fullPage: true,
    });
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("server counteroffer, rejection, missing information and technical HTTP-200 checks", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    const counter = await decide(client.context, staff.context, {
      company: 2,
      revenue: "500000",
      expenses: "400000",
      debt: "20000",
    });
    expect(currentOffer(counter)).toBeTruthy();
    expect(currentRevision(counter)?.assessment?.decision?.outcome).toBe(
      "counteroffer",
    );
    await showApp(client.page, counter);
    await expect(
      client.page.getByRole("heading", {
        name: "Встречное предложение",
        exact: true,
      }),
    ).toBeVisible();
    await uiAction(client.page, "Отклонить предложение");
    expect((await getApp(client.context, counter.id)).status).toBe("declined");
    const rejected = await decide(client.context, staff.context, {
      company: 4,
    });
    await showApp(client.page, rejected);
    await expect(
      client.page.getByRole("heading", { name: "Решение: отказ", exact: true }),
    ).toBeVisible();
    await expect(
      client.page.getByRole("button", { name: "Принять предложение" }),
    ).toHaveCount(0);
    const missing = await create(client.context, {
      company: 3,
      revenue: null,
      expenses: null,
      debt: null,
    });
    expect(missing.status).toBe("needs_info");
    await showApp(client.page, missing);
    await expect(
      client.page.getByRole("link", { name: "Ответить банку", exact: true }),
    ).toBeVisible();
    const technical = await create(client.context, { company: 5 });
    expect(technical.status).toBe("checking");
    await showApp(staff.page, technical, true);
    await expect(
      staff.page.getByText("Техническая ошибка", { exact: true }).first(),
    ).toBeVisible();
    await staff.page
      .getByRole("button", { name: "Взять в работу", exact: true })
      .click();
    await staff.page
      .getByRole("button", { name: "Повторить проверку", exact: true })
      .click();
    await expect(
      staff.page.getByRole("button", {
        name: "Принять решение по правилам",
        exact: true,
      }),
    ).toBeEnabled();
    expect((await getApp(client.context, technical.id)).status).toBe("review");
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("assignment race, forbidden reassignment, queue filters, risk and search", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const first = await actor(browser, sessions, "specialist", baseURL!);
  const second = await actor(browser, sessions, "e2e-specialist", baseURL!);
  try {
    const app = await create(client.context);
    await Promise.all([
      showApp(first.page, app, true),
      showApp(second.page, app, true),
    ]);
    const csrf1 = (
      await (await first.context.request.get("/api/v1/session/csrf/")).json()
    ).csrf_token;
    const csrf2 = (
      await (await second.context.request.get("/api/v1/session/csrf/")).json()
    ).csrf_token;
    const responses = await Promise.all([
      first.context.request.post(
        `/api/v1/staff/applications/${app.id}/claim/`,
        {
          data: { lock_version: app.lock_version },
          headers: { "X-CSRFToken": csrf1 },
        },
      ),
      second.context.request.post(
        `/api/v1/staff/applications/${app.id}/claim/`,
        {
          data: { lock_version: app.lock_version },
          headers: { "X-CSRFToken": csrf2 },
        },
      ),
    ]);
    expect(responses.map((r) => r.status()).sort()).toEqual([200, 409]);
    const winner = responses[0]!.status() === 200 ? first : second;
    const loser = winner === first ? second : first;
    await loser.page.reload();
    await expect(
      loser.page.getByRole("button", { name: "Взять в работу", exact: true }),
    ).toBeDisabled();
    await expect(
      loser.page.getByRole("button", {
        name: "Освободить заявку",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(
      loser.page
        .getByText("Заявка занята другим специалистом.", {
          exact: true,
        })
        .first(),
    ).toBeVisible();
    await winner.page.goto(
      `/staff?assignment=mine&status=review&risk_level=low&search=${app.number}`,
    );
    await expect(
      winner.page.getByRole("link", { name: app.number, exact: true }).first(),
    ).toBeVisible();
    await winner.page
      .getByRole("button", { name: "Свободные", exact: true })
      .click();
    await expect(
      winner.page.getByRole("heading", {
        name: "По выбранным условиям заявок нет",
        exact: true,
      }),
    ).toBeVisible();
  } finally {
    await client.context.close();
    await first.context.close();
    await second.context.close();
  }
});

test("draft version conflict preserves input and requires review; foreign company is isolated", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const outsider = await actor(browser, sessions, "outsider", baseURL!);
  try {
    const app = await post(client.context, "applications/", {
      company: "00000000-0000-0000-0000-000000000001",
      product: "00000000-0000-0000-0000-000000000065",
      amount: "1000000.00",
      term_months: 24,
      purpose: "Concurrency draft",
    });
    await client.page.goto(`/app/loans/${app.id}/edit`);
    await client.page
      .getByLabel("Цель кредита", { exact: true })
      .fill("Мой сохранённый ввод");
    const csrf = (
      await (await client.context.request.get("/api/v1/session/csrf/")).json()
    ).csrf_token;
    const patch = await client.context.request.patch(
      `/api/v1/applications/${app.id}/`,
      {
        data: { purpose: "Другая вкладка", lock_version: app.lock_version },
        headers: { "X-CSRFToken": csrf },
      },
    );
    expect(patch.ok()).toBeTruthy();
    await client.page
      .getByRole("button", { name: "Сохранить черновик", exact: true })
      .click();
    await expect(
      client.page.getByText("Серверные данные изменились", { exact: true }),
    ).toBeVisible();
    await expect(
      client.page.getByLabel("Цель кредита", { exact: true }),
    ).toHaveValue("Мой сохранённый ввод");
    await expect(
      client.page.getByRole("button", {
        name: "Сохранить черновик",
        exact: true,
      }),
    ).toBeDisabled();
    await client.page
      .getByRole("button", {
        name: "Сведения проверены — использовать новую версию",
        exact: true,
      })
      .click();
    await client.page
      .getByRole("button", { name: "Сохранить черновик", exact: true })
      .click();
    await expect(client.page).toHaveURL(new RegExp(`/app/loans/${app.id}$`));
    expect(currentRevision(await getApp(client.context, app.id))?.purpose).toBe(
      "Мой сохранённый ввод",
    );
    await outsider.page.goto(`/app/loans/${app.id}`);
    await expect(outsider.page.getByRole("alert")).toBeVisible();
    await expect(
      outsider.page.getByText("Мой сохранённый ввод", { exact: true }),
    ).toHaveCount(0);
  } finally {
    await client.context.close();
    await outsider.context.close();
  }
});

test("lost issuance response reconciles with real server without second POST", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    const app = await signed(client.context, staff.context);
    await showApp(staff.page, app, true);
    let sent = 0;
    await staff.page.route(
      "**/api/v1/agreements/*/disburse/",
      async (route) => {
        sent++;
        await route.fetch();
        await route.abort("failed");
      },
    );
    await uiAction(staff.page, "Моделировать выдачу");
    await expect(
      staff.page.getByText(/После потери ответа сервер подтвердил/),
    ).toBeVisible();
    expect(sent).toBe(1);
    expect((await getApp(client.context, app.id)).status).toBe("issued");
    await staff.page.reload();
    await expect(
      staff.page.getByRole("button", {
        name: "Моделировать выдачу",
        exact: true,
      }),
    ).toHaveCount(0);
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("pending issuance survives reload and explicit retry uses the same key", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    const app = await signed(client.context, staff.context);
    await showApp(staff.page, app, true);
    let firstKey = "";
    let sent = 0;
    await staff.page.route(
      "**/api/v1/agreements/*/disburse/",
      async (route) => {
        sent++;
        firstKey = route.request().headers()["idempotency-key"]!;
        await route.abort("failed");
      },
    );
    await staff.page
      .getByRole("button", { name: "Моделировать выдачу", exact: true })
      .click();
    await staff.page
      .getByRole("dialog")
      .getByRole("button", { name: "Подтвердить", exact: true })
      .click();
    await expect(staff.page.getByRole("alert")).toBeVisible();
    await staff.page
      .getByRole("dialog")
      .getByRole("button", { name: "Отмена", exact: true })
      .click();
    await staff.page.reload();
    await expect(
      staff.page.getByRole("button", {
        name: "Повторить с тем же ключом",
        exact: true,
      }),
    ).toBeVisible();
    expect(sent).toBe(1);
    await staff.page.unroute("**/api/v1/agreements/*/disburse/");
    const request = staff.page.waitForRequest(
      "**/api/v1/agreements/*/disburse/",
    );
    await uiAction(staff.page, "Повторить с тем же ключом");
    expect((await request).headers()["idempotency-key"]).toBe(firstKey);
    expect((await getApp(client.context, app.id)).status).toBe("issued");
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("responsive layouts, keyboard dialogs, accessibility, empty states and AI assistant", async ({
  browser,
  sessions,
  baseURL,
}, testInfo) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  const outsider = await actor(browser, sessions, "outsider", baseURL!);
  try {
    for (const width of [360, 600, 768, 1024, 1280, 1440]) {
      await client.page.setViewportSize({ width, height: 1000 });
      await client.page.goto("/app/loans/new");
      await expect(
        client.page.getByLabel("Сумма, ₽", { exact: true }),
      ).toBeVisible();
      await expect
        .poll(() =>
          client.page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBeTruthy();
      await client.page.screenshot({
        path: testInfo.outputPath(`form-${width}.png`),
        fullPage: true,
      });
      await staff.page.setViewportSize({ width, height: 1000 });
      await staff.page.goto("/staff");
      await expect(
        staff.page.getByLabel("Поиск по номеру, компании или ИНН", {
          exact: true,
        }),
      ).toBeVisible();
      await expect
        .poll(() =>
          staff.page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBeTruthy();
    }
    await client.page.goto("/app");
    await expect(
      client.page.getByRole("button", { name: "Савелий", exact: true }),
    ).toBeVisible();
    await client.page
      .getByRole("button", { name: "Савелий", exact: true })
      .click();
    await expect(
      client.page.getByRole("dialog", { name: "Савелий, помощник по кредиту" }),
    ).toBeVisible();
    await client.page.keyboard.press("Escape");
    await expect(client.page.getByRole("dialog")).toHaveCount(0);
    await expect(
      client.page.getByRole("button", { name: "Савелий", exact: true }),
    ).toBeFocused();
    await expect(
      staff.page.getByRole("button", { name: "Савелий", exact: true }),
    ).toHaveCount(0);
    await outsider.page.goto("/app/loans");
    await expect(
      outsider.page.getByRole("heading", {
        name: "У вас пока нет заявок и кредитов",
        exact: true,
      }),
    ).toBeVisible();
    for (const page of [client.page, staff.page, outsider.page]) {
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect(
        results.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => n.target),
        })),
      ).toEqual([]);
    }
    await client.page.evaluate(
      () => (document.documentElement.style.zoom = "2"),
    );
    await expect
      .poll(() =>
        client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      )
      .toBeTruthy();
    await client.page.screenshot({
      path: testInfo.outputPath("home-200-percent.png"),
      fullPage: true,
    });
  } finally {
    await client.context.close();
    await staff.context.close();
    await outsider.context.close();
  }
});

test("login CSRF rotation, protected writes, logout and cache isolation", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  try {
    await page.goto("/login");
    await page.getByLabel("Логин", { exact: true }).fill("client");
    await page
      .getByLabel("Пароль", { exact: true })
      .fill(process.env.DEMO_PASSWORD!);
    const login = page.waitForResponse("**/api/v1/session/login/");
    await page
      .getByRole("button", { name: "Войти в кабинет", exact: true })
      .click();
    expect((await login).ok()).toBeTruthy();
    await expect(
      page.getByRole("heading", { name: /Здравствуйте/ }),
    ).toBeVisible();
    const cookies = await context.cookies();
    expect(cookies.find((c) => c.name === "sessionid")?.httpOnly).toBe(true);
    const noCsrf = await context.request.post("/api/v1/applications/", {
      data: {},
    });
    expect(noCsrf.status()).toBe(403);
    await page.getByRole("button", { name: "Выйти", exact: true }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Завершить сессию", exact: true })
      .click();
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Логин", { exact: true }).fill("outsider");
    await page
      .getByLabel("Пароль", { exact: true })
      .fill(process.env.DEMO_PASSWORD!);
    await page
      .getByRole("button", { name: "Войти в кабинет", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: /Здравствуйте/ }),
    ).toBeVisible();
    await expect(page.getByText("Демо · Рост", { exact: true })).toHaveCount(0);
  } finally {
    await context.close();
  }
});

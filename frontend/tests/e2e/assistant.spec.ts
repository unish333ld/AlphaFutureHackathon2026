import { test, expect } from "@playwright/test";

// This deployment check must work even when AI_ENABLED=false or the LLM is offline.
test("Савелий: кнопка и окно доступны без запроса к модели @assistant-ui", async ({
  page,
}, testInfo) => {
  test.skip(
    process.env.E2E_ASSISTANT_ENABLED !== "true",
    "Run against a frontend built with VITE_AI_ASSISTANT_ENABLED=true",
  );
  const errors: string[] = [];
  const mutations: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (
      request.url().includes("/api/v1/assistant/") &&
      !["GET", "HEAD", "OPTIONS"].includes(request.method())
    ) {
      mutations.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });

  await page.goto("/login");
  await page.getByLabel("Логин", { exact: true }).fill("client");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Войти в кабинет" }).click();
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();

  const trigger = page.getByRole("button", { name: "Савелий", exact: true });
  const widget = page.getByRole("dialog", {
    name: "Савелий, помощник по кредиту",
  });
  await expect(trigger).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(widget).toHaveCount(0);
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(widget).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(
    widget.getByRole("textbox", { name: "Сообщение Савелию" }),
  ).toBeVisible();
  await widget.evaluate((node) =>
    Promise.all(node.getAnimations().map((item) => item.finished)),
  );
  await widget.screenshot({ path: testInfo.outputPath("saveliy-window.png") });
  await page.keyboard.press("Escape");
  await expect(widget).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await page.reload();
  await expect(trigger).toBeVisible();
  expect(mutations).toEqual([]);
  expect(errors).toEqual([]);
});

test("Савелий: окно, сообщение и история @assistant", async ({ page }) => {
  test.skip(
    !process.env.E2E_ASSISTANT_ENABLED,
    "Run against a local build with assistant enabled",
  );
  test.setTimeout(120_000);

  await page.goto("/login");
  await page.getByLabel("Логин", { exact: true }).fill("client");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Войти в кабинет" }).click();
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Савелий", exact: true }).click();
  const widget = page.getByRole("dialog", {
    name: "Савелий, помощник по кредиту",
  });
  await expect(widget).toBeVisible();
  await widget.evaluate((node) =>
    Promise.all(node.getAnimations().map((item) => item.finished)),
  );
  await expect(widget.getByRole("button", { name: "Новый чат" })).toBeVisible();

  const before = await widget.boundingBox();
  expect(before).not.toBeNull();
  const grab = widget.getByLabel("Переместить окно Савелия стрелками");
  await grab.focus();
  await page.keyboard.press("ArrowLeft");
  const afterMove = await widget.boundingBox();
  expect(afterMove!.x).toBeLessThan(before!.x);
  const grabBox = await grab.boundingBox();
  await page.mouse.move(
    grabBox!.x + grabBox!.width / 2,
    grabBox!.y + grabBox!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    grabBox!.x + grabBox!.width / 2 - 35,
    grabBox!.y + grabBox!.height / 2 - 25,
  );
  await page.mouse.up();
  const afterPointerMove = await widget.boundingBox();
  expect(afterPointerMove!.x).toBeLessThan(afterMove!.x);
  expect(afterPointerMove!.y).toBeLessThan(afterMove!.y);
  const resize = widget.getByRole("button", {
    name: "Изменить размер окна Савелия",
  });
  await resize.focus();
  await page.keyboard.press("ArrowLeft");
  const afterResize = await widget.boundingBox();
  expect(afterResize!.width).toBeLessThan(afterPointerMove!.width);
  const resizeBox = await resize.boundingBox();
  await page.mouse.move(resizeBox!.x + 12, resizeBox!.y + 12);
  await page.mouse.down();
  await page.mouse.move(resizeBox!.x + 42, resizeBox!.y + 32);
  await page.mouse.up();
  const afterPointerResize = await widget.boundingBox();
  expect(afterPointerResize!.width).toBeGreaterThan(afterResize!.width);

  const prompt = "Какие данные нужны для заявки?";
  await widget.getByRole("button", { name: prompt }).click();
  const input = widget.getByRole("textbox", { name: "Сообщение Савелию" });
  await expect(input).toHaveValue(prompt);
  await widget.getByRole("button", { name: "Отправить" }).click();
  await expect(
    widget.locator('[class*="userMessage"]').getByText(prompt, { exact: true }),
  ).toBeVisible();
  await expect(widget.locator('[class*="assistantMessage"]')).toHaveCount(1, {
    timeout: 90_000,
  });

  await input.fill("Какие кредитные продукты доступны?");
  await widget.getByRole("button", { name: "Отправить" }).click();
  await expect(widget.getByText("Демонстрационные продукты")).toBeVisible({
    timeout: 90_000,
  });

  await widget.getByRole("button", { name: "Закрыть Савелия" }).click();
  await page.reload();
  await page.getByRole("button", { name: "Савелий", exact: true }).click();
  await widget.locator('[class*="historyItem"]').first().click();
  await expect(
    widget.locator('[class*="userMessage"]').getByText(prompt, { exact: true }),
  ).toBeVisible();
});

test("Предложенный Савелием черновик требует проверки в форме @assistant", async ({
  page,
}) => {
  test.skip(
    !process.env.E2E_ASSISTANT_ENABLED,
    "Run against a local build with assistant enabled",
  );
  await page.goto("/login");
  await page.getByLabel("Логин", { exact: true }).fill("client");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Войти в кабинет" }).click();
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();
  const data = await page.evaluate(async () => {
    const [companies, products, applications] = await Promise.all([
      fetch("/api/v1/companies/").then((r) => r.json()),
      fetch("/api/v1/products/").then((r) => r.json()),
      fetch("/api/v1/applications/").then((r) => r.json()),
    ]);
    return {
      company: companies.results[0].id as string,
      product: products.results[0].id as string,
      applications: applications.count as number,
    };
  });
  const draft = {
    company: data.company,
    product: data.product,
    amount: "1000000.00",
    term_months: 24,
    purpose: "Пополнение оборотных средств",
    requires_user_confirmation: true,
  };
  const now = new Date().toISOString();
  await page.route(
    /\/assistant\/conversations\/[0-9a-f-]+\/messages\//,
    async (route) => {
      const id = /conversations\/([0-9a-f-]+)\/messages\//.exec(
        route.request().url(),
      )![1];
      const rows = [
        {
          id: "11111111-1111-4111-8111-111111111111",
          role: "user",
          content: "Подготовь черновик",
          facts: [],
          suggested_draft: {},
          created_at: now,
        },
        {
          id: "22222222-2222-4222-8222-222222222222",
          role: "assistant",
          content: "Проверьте предложенные поля в заявке.",
          facts: [],
          suggested_draft: draft,
          created_at: now,
        },
      ];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          route.request().method() === "POST"
            ? {
                conversation_id: id,
                version: 1,
                model_status: "available",
                message: rows[1],
              }
            : { count: 2, next: null, previous: null, results: rows },
        ),
      });
    },
  );
  await page.getByRole("button", { name: "Савелий", exact: true }).click();
  const widget = page.getByRole("dialog", {
    name: "Савелий, помощник по кредиту",
  });
  await widget
    .getByRole("textbox", { name: "Сообщение Савелию" })
    .fill("Подготовь черновик");
  await widget.getByRole("button", { name: "Отправить" }).click();
  await widget.getByRole("button", { name: "Проверить в заявке" }).click();
  await expect(page).toHaveURL(/\/app\/loans\/new/);
  await expect(page.getByLabel("Сумма, ₽")).toHaveValue("1000000.00");
  await expect(page.getByLabel("Срок, месяцев")).toHaveValue("24");
  await expect(page.getByLabel("Цель кредита")).toHaveValue(draft.purpose);
  const after = await page.evaluate(async () =>
    fetch("/api/v1/applications/").then((r) => r.json()),
  );
  expect(after.count).toBe(data.applications);
});

test("Савелий помещается на узком экране @assistant", async ({ page }) => {
  test.skip(
    !process.env.E2E_ASSISTANT_ENABLED,
    "Run against a local build with assistant enabled",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByLabel("Логин", { exact: true }).fill("client");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Войти в кабинет" }).click();
  await page.getByRole("button", { name: "Савелий", exact: true }).click();
  const widget = page.getByRole("dialog", {
    name: "Савелий, помощник по кредиту",
  });
  await widget.evaluate((node) =>
    Promise.all(node.getAnimations().map((item) => item.finished)),
  );
  const box = await widget.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  await expect(
    widget.getByRole("button", { name: "Изменить размер окна Савелия" }),
  ).toBeHidden();
  await widget.getByRole("button", { name: "История" }).click();
  await expect(widget.getByRole("button", { name: "Новый чат" })).toBeVisible();
});

test("Савелий сохраняет состояние при сворачивании и в низком окне @assistant", async ({
  page,
}) => {
  test.skip(!process.env.E2E_ASSISTANT_ENABLED, "Assistant must be enabled");
  await page.setViewportSize({ width: 980, height: 360 });
  await page.goto("/login");
  await page.getByLabel("Логин", { exact: true }).fill("client");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Войти в кабинет" }).click();
  await page.route(/\/api\/v1\/assistant\/conversations\/\?/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        count: 25,
        next: null,
        previous: null,
        results: Array.from({ length: 25 }, (_, index) => ({
          id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
          company: "00000000-0000-4000-8000-000000000001",
          application: null,
          version: 0,
          updated_at: new Date().toISOString(),
        })),
      }),
    });
  });
  await page.getByRole("button", { name: "Савелий", exact: true }).click();
  const widget = page.getByRole("dialog", {
    name: "Савелий, помощник по кредиту",
  });
  await expect(widget).toBeVisible();
  await widget.evaluate((node) =>
    Promise.all(node.getAnimations().map((item) => item.finished)),
  );
  const rect = await widget.boundingBox();
  expect(rect!.y).toBeGreaterThanOrEqual(0);
  expect(rect!.y + rect!.height).toBeLessThanOrEqual(360);
  await expect(
    widget.getByRole("button", { name: "Отправить" }),
  ).toBeInViewport();
  const promptStrip = widget.locator("#saveliy-prompts");
  await promptStrip.hover();
  await page.mouse.wheel(0, 350);
  await expect
    .poll(() => promptStrip.evaluate((node) => node.scrollLeft))
    .toBeGreaterThan(0);
  const history = widget.locator('[class*="historyList"]');
  await expect(history.locator('[class*="historyItem"]')).toHaveCount(25);
  await history.hover();
  await page.mouse.wheel(0, 350);
  await expect
    .poll(() => history.evaluate((node) => node.scrollTop))
    .toBeGreaterThan(0);
  await widget
    .getByRole("textbox", { name: "Сообщение Савелию" })
    .fill("Вопрос сохранится");
  await widget.getByRole("button", { name: "Свернуть частые вопросы" }).click();
  await expect(
    widget.getByRole("button", { name: "Развернуть частые вопросы" }),
  ).toBeVisible();
  await widget.getByRole("button", { name: "Свернуть Савелия" }).click();
  await expect(widget).toBeHidden();
  await page.getByRole("button", { name: "Савелий", exact: true }).click();
  await expect(widget).toBeVisible();
  await widget.evaluate((node) =>
    Promise.all(node.getAnimations().map((item) => item.finished)),
  );
  await expect(
    widget.getByRole("textbox", { name: "Сообщение Савелию" }),
  ).toHaveValue("Вопрос сохранится");
  await expect(
    widget.getByRole("button", { name: "Развернуть частые вопросы" }),
  ).toBeVisible();
  const restored = await widget.boundingBox();
  expect(restored!.x).toBeCloseTo(rect!.x, 0);
  expect(restored!.width).toBeCloseTo(rect!.width, 0);
  await page.setViewportSize({ width: 390, height: 260 });
  await expect(
    widget.getByRole("button", { name: "Отправить" }),
  ).toBeInViewport();
  const compact = await widget.boundingBox();
  expect(compact!.y).toBeGreaterThanOrEqual(0);
  expect(compact!.y + compact!.height).toBeLessThanOrEqual(260);
  await page.setViewportSize({ width: 320, height: 180 });
  await expect(
    widget.getByRole("button", { name: "Отправить" }),
  ).toBeInViewport();
  const tiny = await widget.boundingBox();
  expect(tiny!.y).toBeGreaterThanOrEqual(0);
  expect(tiny!.y + tiny!.height).toBeLessThanOrEqual(180);
});

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { test, expect, actor, create } from "./fixtures";
import type { AssistantReply, Product } from "../../src/shared/api/client";

const widget = (page: Page) =>
  page.getByRole("dialog", {
    name: "Савелий, помощник по кредиту",
    exact: true,
  });
async function open(page: Page) {
  await page.getByRole("button", { name: "Савелий", exact: true }).click();
  await expect(widget(page)).toBeVisible();
}
async function ask(page: Page, text: string) {
  await widget(page)
    .getByLabel("Сообщение Савелию", { exact: true })
    .fill(text);
  const response = page.waitForResponse(
    (item) =>
      item.request().method() === "POST" &&
      /assistant\/conversations\/.+\/messages\//.test(item.url()),
  );
  await widget(page)
    .getByRole("button", { name: "Отправить", exact: true })
    .click();
  const result = await response;
  expect(result.status(), await result.text()).toBe(200);
  await expect(
    widget(page).getByText("Ответ получен.", { exact: true }),
  ).toBeVisible();
  return (await result.json()) as AssistantReply;
}
test.beforeEach(() => {
  test.skip(
    process.env.E2E_ASSISTANT_ENABLED !== "true",
    "Frontend must be built with assistant enabled",
  );
});

test("Савелий: доступен без вызова модели, клавиатура и адаптивность @assistant-ui", async ({
  browser,
  sessions,
  baseURL,
}, info) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const mutations: string[] = [];
  client.page.on("request", (request) => {
    if (request.url().includes("/assistant/") && request.method() !== "GET")
      mutations.push(request.method());
  });
  try {
    await client.page.goto("/app");
    const trigger = client.page.getByRole("button", {
      name: "Савелий",
      exact: true,
    });
    for (const width of [360, 768, 1024, 1180, 1200, 1280, 1440]) {
      await client.page.setViewportSize({ width, height: 900 });
      await trigger.focus();
      await client.page.keyboard.press("Enter");
      await expect(widget(client.page)).toBeVisible();
      const rect = await widget(client.page).boundingBox();
      expect(rect!.x).toBeGreaterThanOrEqual(0);
      expect(rect!.x + rect!.width).toBeLessThanOrEqual(width);
      expect(
        await client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width >= 1180) {
        const main = await client.page.getByRole("main").boundingBox();
        expect(main!.x + main!.width).toBeLessThanOrEqual(rect!.x);
      }
      await expect(
        widget(client.page).getByRole("button", {
          name: "Отправить",
          exact: true,
        }),
      ).toBeInViewport();
      if (width === 360 || width === 1440) {
        const result = await new AxeBuilder({ page: client.page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        expect(result.violations.map((v) => v.id)).toEqual([]);
        await client.page.screenshot({
          path: info.outputPath(`assistant-${width}.png`),
          fullPage: true,
        });
      }
      await client.page.keyboard.press("Escape");
      await expect(widget(client.page)).toHaveCount(0);
      await expect(trigger).toBeFocused();
    }
    await client.page.setViewportSize({ width: 768, height: 360 });
    await trigger.click();
    const input = widget(client.page).getByLabel("Сообщение Савелию", {
      exact: true,
    });
    await input.scrollIntoViewIfNeeded();
    await input.fill("Проверка низкого экрана");
    const send = widget(client.page).getByRole("button", {
      name: "Отправить",
      exact: true,
    });
    await send.scrollIntoViewIfNeeded();
    await expect(send).toBeInViewport();
    await client.page.keyboard.press("Escape");
    await expect(widget(client.page)).toHaveCount(0);
    expect(mutations).toEqual([]);
  } finally {
    await client.context.close();
  }
});

test("read-only draft suggestion → explicit preview → ordinary form @assistant @critical", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    await client.page.goto("/app");
    const before = await (
      await client.context.request.get("/api/v1/applications/")
    ).json();
    await open(client.page);
    await ask(client.page, "Нужен миллион на закупку товара на год");
    await widget(client.page)
      .getByRole("button", { name: "Оборотные средства · демо", exact: true })
      .click();
    await expect(
      widget(client.page).getByRole("button", { name: "Проверить в заявке" }),
    ).toBeVisible();
    await widget(client.page)
      .getByRole("button", { name: "Проверить в заявке" })
      .click();
    const preview = client.page.getByRole("dialog", {
      name: "Проверить предложенные изменения",
      exact: true,
    });
    await expect(preview).toContainText("Не задано → 1000000.00");
    await preview.getByRole("button", { name: "Перенести в форму" }).click();
    await expect(client.page).toHaveURL(/\/app\/loans\/new/);
    await expect(
      client.page.getByLabel("Сумма, ₽", { exact: true }),
    ).toHaveValue("1000000.00");
    await expect(
      client.page.getByLabel("Срок, месяцев", { exact: true }),
    ).toHaveValue("12");
    await expect(
      client.page.getByLabel("Цель кредита", { exact: true }),
    ).toHaveValue("Закупка товара");
    await expect(
      client.page.getByLabel("Месячная выручка, ₽", { exact: true }),
    ).toHaveValue("");
    const after = await (
      await client.context.request.get("/api/v1/applications/")
    ).json();
    expect(after.count).toBe(before.count);
    expect(
      await client.page.evaluate(() =>
        Object.keys(sessionStorage)
          .concat(Object.keys(localStorage))
          .some((key) => /draft|message|conversation/i.test(key)),
      ),
    ).toBe(false);
  } finally {
    await client.context.close();
  }
});

test("form changed after answer is preserved, old suggestion cannot overwrite it @assistant @critical", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const catalog = await (
      await client.context.request.get("/api/v1/products/")
    ).json();
    const product = catalog.results.find(
      (item: Product) => item.code === "working-capital",
    );
    await client.page.goto(
      `/app/loans/new?product=${product.id}&company=00000000-0000-0000-0000-000000000001`,
    );
    await expect(
      client.page.getByLabel("Сумма, ₽", { exact: true }),
    ).toHaveValue("1000000.00");
    await open(client.page);
    await ask(client.page, "Оборотные: нужен миллион рублей на 12 месяцев");
    await expect(
      widget(client.page).getByRole("button", { name: "Проверить в заявке" }),
    ).toBeVisible();
    await widget(client.page)
      .getByRole("button", { name: "Закрыть Савелия" })
      .click();
    await client.page.getByLabel("Сумма, ₽", { exact: true }).fill("1700000");
    await open(client.page);
    await widget(client.page)
      .getByRole("button", { name: "Проверить в заявке" })
      .click();
    await expect(
      widget(client.page).getByText(/Форма изменилась после вопроса/),
    ).toBeVisible();
    await widget(client.page)
      .getByRole("button", { name: "Закрыть Савелия" })
      .click();
    await expect(
      client.page.getByLabel("Сумма, ₽", { exact: true }),
    ).toHaveValue("1700000");
  } finally {
    await client.context.close();
  }
});

test("confirmation applies only permitted fields and preserves monthly inputs @assistant", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const catalog = await (
      await client.context.request.get("/api/v1/products/")
    ).json();
    const product = catalog.results.find(
      (item: Product) => item.code === "working-capital",
    );
    await client.page.goto(
      `/app/loans/new?product=${product.id}&company=00000000-0000-0000-0000-000000000001`,
    );
    await client.page
      .getByLabel("Месячная выручка, ₽", { exact: true })
      .fill("1234567");
    await open(client.page);
    await ask(client.page, "Оборотные: нужен миллион рублей на 12 месяцев");
    await widget(client.page)
      .getByRole("button", { name: "Проверить в заявке" })
      .click();
    const preview = client.page.getByRole("dialog", {
      name: "Проверить предложенные изменения",
      exact: true,
    });
    await expect(preview).toContainText("24 → 12");
    await preview.getByRole("button", { name: "Перенести в форму" }).click();
    await expect(
      client.page.getByLabel("Срок, месяцев", { exact: true }),
    ).toHaveValue("12");
    await expect(
      client.page.getByLabel("Месячная выручка, ₽", { exact: true }),
    ).toHaveValue("1234567");
  } finally {
    await client.context.close();
  }
});

test("route switch changes application context; history names actual application @assistant", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const first = await create(client.context),
      second = await create(client.context);
    await client.page.goto(`/app/loans/${first.id}`);
    await open(client.page);
    const reply = await ask(client.page, "Какой статус моей заявки?");
    expect(reply.message.application_id).toBe(first.id);
    await expect(widget(client.page).getByRole("heading")).toContainText(
      first.number,
    );
    await widget(client.page)
      .getByRole("button", { name: "Закрыть Савелия" })
      .click();
    await client.page
      .getByRole("link", { name: "Заявки и кредиты", exact: true })
      .first()
      .click();
    await client.page
      .getByRole("link")
      .filter({ hasText: second.number })
      .first()
      .click();
    await open(client.page);
    await expect(widget(client.page).getByRole("heading")).toContainText(
      second.number,
    );
    const fresh = await ask(client.page, "Какой статус моей заявки?");
    expect(fresh.message.application_id).toBe(second.id);
    await widget(client.page)
      .getByRole("button", { name: "История", exact: true })
      .click();
    await expect(
      widget(client.page).getByRole("button", {
        name: new RegExp(first.number),
      }),
    ).toBeVisible();
  } finally {
    await client.context.close();
  }
});

test("lost successful answer is recovered from real server history without repeat @assistant", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  let posts = 0;
  try {
    await client.page.goto("/app");
    await open(client.page);
    await client.page.route(
      /\/assistant\/conversations\/.+\/messages\//,
      async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        posts++;
        await route.fetch();
        await route.abort("failed");
      },
    );
    await widget(client.page)
      .getByLabel("Сообщение Савелию", { exact: true })
      .fill("Какие данные нужны для заявки?");
    await widget(client.page)
      .getByRole("button", { name: "Отправить", exact: true })
      .click();
    await expect(
      widget(client.page).getByText(
        "Ответ найден в истории. Повторная отправка не требуется.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      widget(client.page).getByLabel("Сообщение Савелию", { exact: true }),
    ).toHaveValue("");
    expect(posts).toBe(1);
  } finally {
    await client.context.close();
  }
});

for (const status of [409, 429, 503]) {
  test(`assistant HTTP ${status} preserves input and requires manual retry @assistant`, async ({
    browser,
    sessions,
    baseURL,
  }) => {
    const client = await actor(browser, sessions, "client", baseURL!);
    try {
      await client.page.goto("/app");
      await open(client.page);
      let posts = 0;
      await client.page.route(
        /\/assistant\/conversations\/.+\/messages\//,
        async (route) => {
          if (route.request().method() !== "POST") return route.continue();
          posts++;
          await route.fulfill({
            status,
            headers: status === 429 ? { "Retry-After": "2" } : {},
            json: { detail: "QA error" },
          });
        },
      );
      const input = widget(client.page).getByLabel("Сообщение Савелию", {
        exact: true,
      });
      await input.fill("Ввод должен сохраниться");
      const injected = client.page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          /assistant\/conversations\/.+\/messages\//.test(response.url()) &&
          response.status() === status,
      );
      await widget(client.page)
        .getByRole("button", { name: "Отправить", exact: true })
        .click();
      await injected;
      await expect(widget(client.page).getByRole("alert")).toBeVisible();
      await expect(input).toHaveValue("Ввод должен сохраниться");
      if (status === 429) {
        await expect(
          widget(client.page).getByText(/Повторная отправка доступна через/),
        ).toBeVisible();
        await expect(
          widget(client.page).getByRole("button", {
            name: "Отправить",
            exact: true,
          }),
        ).toBeDisabled();
      }
      expect(posts).toBe(1);
    } finally {
      await client.context.close();
    }
  });
}

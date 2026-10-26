import AxeBuilder from "@axe-core/playwright";
import type { BrowserContext, Page } from "@playwright/test";
import { test, expect, actor, create } from "./fixtures";
import type { AssistantStep } from "../../src/shared/api/client";

const panel = (page: Page) =>
  page.getByRole("dialog", { name: "Помощник по кредиту", exact: true });
async function open(page: Page) {
  await page.getByRole("button", { name: "Помощник по кредиту" }).click();
  await expect(panel(page)).toBeVisible();
}
async function current(
  context: BrowserContext,
  appId: string,
  company = "00000000-0000-0000-0000-000000000001",
) {
  const csrf = await context.request.get("/api/v1/session/csrf/");
  const value = await context.request.post(
    "/api/v1/assistant/conversations/current/",
    {
      data: { company_id: company, application_id: appId },
      headers: { "X-CSRFToken": (await csrf.json()).csrf_token },
    },
  );
  expect(value.ok(), await value.text()).toBeTruthy();
  return value.json() as Promise<AssistantStep>;
}
async function postStep(
  context: BrowserContext,
  step: AssistantStep,
  payload: { action_id: string } | { text: string },
) {
  const csrf = await context.request.get("/api/v1/session/csrf/");
  return context.request.post(
    `/api/v1/assistant/conversations/${step.conversation_id}/step/`,
    {
      data: {
        expected_version: step.version,
        step_id: step.step_id,
        request_id: crypto.randomUUID(),
        ...payload,
      },
      headers: { "X-CSRFToken": (await csrf.json()).csrf_token },
    },
  );
}
test.beforeEach(() => {
  test.skip(
    process.env.E2E_ASSISTANT_ENABLED !== "true",
    "Requires the assistant-enabled frontend build",
  );
});

test("server choices, input and draft preview use the current step @assistant @critical", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const app = await create(client.context);
    await client.page.goto(`/app/loans/${app.id}`);
    const before = await (
      await client.context.request.get("/api/v1/applications/")
    ).json();
    await open(client.page);
    await expect(panel(client.page).getByText("С чем помочь?")).toBeVisible();
    await expect(panel(client.page).getByRole("textbox")).toHaveCount(0);
    const old = await current(client.context, app.id);
    await panel(client.page)
      .getByRole("button", { name: "Подготовить заявку" })
      .click();
    await expect(
      panel(client.page).getByText("Для какой задачи нужен кредит?"),
    ).toBeVisible();
    const stale = await postStep(client.context, old, { action_id: "prepare" });
    expect(stale.status()).toBe(409);
    const choices = panel(client.page).getByRole("button", {
      name: /Оборотные средства/,
    });
    await expect(choices).toBeEnabled();
    await choices.click();
    await expect(
      panel(client.page).getByLabel("Какая сумма нужна?"),
    ).toBeVisible();
    await panel(client.page).getByLabel("Какая сумма нужна?").fill("1000000");
    await panel(client.page)
      .getByRole("button", { name: "Продолжить" })
      .click();
    await expect(panel(client.page).getByLabel("На какой срок?")).toBeVisible();
    await panel(client.page).getByLabel("На какой срок?").fill("12");
    await panel(client.page)
      .getByRole("button", { name: "Продолжить" })
      .click();
    await expect(
      panel(client.page).getByText("Параметры готовы", { exact: false }),
    ).toBeVisible();
    await panel(client.page)
      .getByRole("button", { name: "Проверить параметры заявки" })
      .click();
    const preview = client.page.getByRole("dialog", {
      name: "Проверить предложенные параметры",
    });
    await expect(preview).toContainText("1000000.00");
    await preview.getByRole("button", { name: "Перенести в форму" }).click();
    await expect(client.page).toHaveURL(/\/app\/loans\/new/);
    await expect(
      client.page.getByLabel("Сумма, ₽", { exact: true }),
    ).toHaveValue("1000000.00");
    await expect(
      client.page.getByLabel("Срок, месяцев", { exact: true }),
    ).toHaveValue("12");
    await expect(
      client.page.getByLabel("Месячная выручка, ₽", { exact: true }),
    ).toHaveValue("");
    const after = await (
      await client.context.request.get("/api/v1/applications/")
    ).json();
    expect(after.count).toBe(before.count);
  } finally {
    await client.context.close();
  }
});

test("the current step survives reload and duplicate clicks do not send twice @assistant", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const app = await create(client.context);
    await client.page.goto(`/app/loans/${app.id}`);
    await open(client.page);
    await expect(panel(client.page).getByText("С чем помочь?")).toBeVisible();
    let posts = 0;
    client.page.on("request", (request) => {
      if (
        /assistant\/conversations\/.+\/step\/$/.test(request.url()) &&
        request.method() === "POST"
      )
        posts++;
    });
    const choice = panel(client.page).getByRole("button", {
      name: "Рассчитать платёж",
    });
    await choice.dblclick();
    await expect(
      panel(client.page).getByText("Для какой задачи нужен кредит?"),
    ).toBeVisible();
    expect(posts).toBe(1);
    await client.page.reload();
    await open(client.page);
    await expect(
      panel(client.page).getByText("Для какой задачи нужен кредит?"),
    ).toBeVisible();
    await expect(panel(client.page).getByRole("textbox")).toHaveCount(0);
  } finally {
    await client.context.close();
  }
});

test("input is preserved after a network failure, and the user can check server state @assistant", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const app = await create(client.context);
    await client.page.goto(`/app/loans/${app.id}`);
    await open(client.page);
    await expect(panel(client.page).getByText("С чем помочь?")).toBeVisible();
    await panel(client.page)
      .getByRole("button", { name: "Задать вопрос" })
      .click();
    const field = panel(client.page).getByLabel("Что хотите узнать?");
    await field.fill("Какие документы нужны?");
    await client.page.route(
      "**/api/v1/assistant/conversations/*/step/",
      async (route) => {
        if (route.request().method() === "POST") await route.abort("failed");
        else await route.continue();
      },
    );
    await panel(client.page)
      .getByRole("button", { name: "Продолжить" })
      .click();
    await expect(field).toHaveValue("Какие документы нужны?");
    await expect(
      panel(client.page).getByRole("button", { name: "Проверить состояние" }),
    ).toBeVisible();
    await client.page.unroute("**/api/v1/assistant/conversations/*/step/");
  } finally {
    await client.context.close();
  }
});

test("an unavailable opening can be retried manually without a fabricated step @assistant", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const app = await create(client.context);
    await client.page.goto(`/app/loans/${app.id}`);
    await client.page.route(
      "**/api/v1/assistant/conversations/current/",
      (route) =>
        route.fulfill({
          status: 503,
          json: { detail: "Помощник временно недоступен." },
        }),
    );
    await open(client.page);
    await expect(panel(client.page).getByRole("alert")).toContainText(
      "Помощник сейчас недоступен.",
    );
    await expect(
      panel(client.page).getByRole("button", {
        name: "Подготовить заявку",
        exact: true,
      }),
    ).toHaveCount(0);
    await client.page.unroute("**/api/v1/assistant/conversations/current/");
    await panel(client.page)
      .getByRole("button", {
        name: "Попробовать подключиться снова",
        exact: true,
      })
      .click();
    await expect(
      panel(client.page).getByText("С чем помочь?", { exact: true }),
    ).toBeVisible();
  } finally {
    await client.context.close();
  }
});

test("changing page during a delayed response restores usable actions in the new context @assistant", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  let release = () => {};
  try {
    await client.page.setViewportSize({ width: 1440, height: 900 });
    const app = await create(client.context);
    const nextApp = await create(client.context);
    await client.page.goto(`/app/loans/${app.id}`);
    await open(client.page);
    await expect(panel(client.page).getByText("С чем помочь?")).toBeVisible();
    let entered = () => {};
    const waiting = new Promise<void>((resolve) => {
      entered = resolve;
    });
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await client.page.route(
      "**/api/v1/assistant/conversations/*/step/",
      async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        const response = await route.fetch();
        entered();
        await gate;
        await route.fulfill({ response }).catch(() => {});
      },
    );
    await panel(client.page)
      .getByRole("button", { name: "Подготовить заявку" })
      .click();
    await waiting;
    const resumed = client.page.waitForResponse(
      (response) =>
        response.url().endsWith("/assistant/conversations/current/") &&
        response.request().postDataJSON()?.application_id === nextApp.id &&
        response.ok(),
    );
    await client.page
      .getByRole("navigation", { name: "Основная навигация" })
      .getByRole("link", { name: "Заявки и кредиты", exact: true })
      .click();
    await expect(client.page).toHaveURL(/\/app\/loans$/);
    await client.page
      .getByRole("link", { name: new RegExp(nextApp.number) })
      .click();
    await expect(client.page).toHaveURL(
      new RegExp(`/app/loans/${nextApp.id}/?$`),
    );
    const currentResponse = await resumed;
    const currentState = (await currentResponse.json()) as AssistantStep;
    await expect(
      panel(client.page).getByRole("button", {
        name: currentState.choices[0]!.label,
        exact: true,
      }),
    ).toBeEnabled();
    release();
    await expect(
      panel(client.page).getByRole("button", {
        name: currentState.choices[0]!.label,
        exact: true,
      }),
    ).toBeEnabled();
  } finally {
    release();
    await client.context.close();
  }
});

test("assistant panel fits viewports, uses keyboard focus and has no old chat controls @assistant-ui", async ({
  browser,
  sessions,
  baseURL,
}, info) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    await client.page.goto("/app");
    for (const width of [360, 390, 768, 1024, 1440]) {
      await client.page.setViewportSize({ width, height: 900 });
      await open(client.page);
      await expect(panel(client.page)).toHaveCSS(
        "transform",
        "matrix(1, 0, 0, 1, 0, 0)",
      );
      await expect(
        panel(client.page).getByText("История", { exact: true }),
      ).toHaveCount(0);
      await expect(
        panel(client.page).getByRole("button", { name: "Новый чат" }),
      ).toHaveCount(0);
      await expect(
        panel(client.page).getByRole("button", { name: "Удалить диалог" }),
      ).toHaveCount(0);
      const box = await panel(client.page).boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      expect(
        await client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width === 360 || width === 1440) {
        const result = await new AxeBuilder({ page: client.page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        expect(
          result.violations.map((value) => ({
            id: value.id,
            nodes: value.nodes.map((node) => ({
              target: node.target,
              html: node.html,
            })),
          })),
        ).toEqual([]);
        await client.page.screenshot({
          path: info.outputPath(`assistant-${width}.png`),
        });
      }
      await client.page.keyboard.press("Escape");
      await expect(panel(client.page)).toBeHidden();
      if (width <= 1100)
        await expect
          .poll(async () => {
            const box = await client.page
              .getByRole("button", { name: "Помощник по кредиту" })
              .boundingBox();
            return box?.width;
          })
          .toBe(48);
      else
        await expect(
          client.page.getByRole("button", {
            name: "Помощник по кредиту",
            exact: true,
          }),
        ).toContainText("Помощник по кредиту");
    }
  } finally {
    await client.context.close();
  }
});

test("a typed question receives a real model response with server product facts @assistant-live", async ({
  browser,
  sessions,
  baseURL,
}) => {
  test.skip(
    process.env.E2E_LIVE_MODEL !== "true",
    "Requires a configured real model",
  );
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    const app = await create(client.context);
    await client.page.goto(`/app/loans/${app.id}`);
    await open(client.page);
    await panel(client.page)
      .getByRole("button", { name: "Задать вопрос", exact: true })
      .click();
    await panel(client.page)
      .getByRole("textbox", { name: "Что хотите узнать?", exact: true })
      .fill("Какие кредитные продукты доступны?");
    const answering = client.page.waitForResponse(
      (response) =>
        /assistant\/conversations\/.+\/step\/$/.test(response.url()) &&
        response.request().method() === "POST",
      { timeout: 90_000 },
    );
    await panel(client.page)
      .getByRole("button", { name: "Продолжить", exact: true })
      .click();
    const response = await answering;
    expect(response.ok()).toBe(true);
    const result = (await response.json()) as AssistantStep;
    expect(result.mode, result.error_code || result.prompt).toBe("result");
    expect(result.message?.model_status).toBe("available");
    expect(
      result.message?.facts.some(
        (fact) => fact.source === "list_credit_products",
      ),
    ).toBe(true);
    await expect(
      panel(client.page).getByText("Оборотные средства", { exact: true }),
    ).toBeVisible();
  } finally {
    await client.context.close();
  }
});

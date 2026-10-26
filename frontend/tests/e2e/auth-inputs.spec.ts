import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Credential entry is intentionally excluded from trace/screenshot artifacts.
test.use({
  storageState: { cookies: [], origins: [] },
  trace: "off",
  screenshot: "off",
});

test("wrong password is cleared and the next typed password logs in", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Клиент", exact: true }).click();
  const password = page.getByLabel("Пароль", { exact: true });
  await password.pressSequentially("qa-intentionally-incorrect-password");
  await page
    .getByRole("button", { name: "Войти в кабинет", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Неверные учётные данные",
  );
  await expect(
    page.getByRole("button", { name: "Войти в кабинет", exact: true }),
  ).toBeEnabled();
  await expect(password).toBeEmpty();
  await password.focus();
  await expect(password).toBeEmpty();
  await password.pressSequentially(process.env.DEMO_PASSWORD!);
  await password.press("Enter");
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();
});

test("required login errors are associated with fields and typing clears them", async ({
  page,
}) => {
  await page.goto("/login");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations.map((item) => item.id),
  ).toEqual([]);
  await page
    .getByRole("button", { name: "Войти в кабинет", exact: true })
    .click();
  const username = page.getByLabel("Логин", { exact: true });
  const password = page.getByLabel("Пароль", { exact: true });
  await expect(username).toHaveAttribute("aria-invalid", "true");
  await expect(password).toHaveAttribute("aria-invalid", "true");
  await expect(username).toBeEnabled();
  await expect(password).toBeEnabled();
  await username.pressSequentially("client");
  await password.pressSequentially(process.env.DEMO_PASSWORD!);
  await expect(username).toHaveValue("client");
  expect(
    (await password.inputValue()) === process.env.DEMO_PASSWORD,
  ).toBeTruthy();
  await password.press("Enter");
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();
});

test("profile selection, bulk text insertion and password visibility preserve credentials", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Специалист", exact: true }).click();
  await page.getByRole("button", { name: "Клиент", exact: true }).click();
  const username = page.getByLabel("Логин", { exact: true });
  await expect(username).toHaveValue("client");
  const password = page.getByLabel("Пароль", { exact: true });
  await password.focus();
  await page.keyboard.insertText(process.env.DEMO_PASSWORD!);
  await page
    .getByRole("button", { name: "Показать пароль", exact: true })
    .click();
  await expect(password).toHaveAttribute("type", "text");
  expect(
    (await password.inputValue()) === process.env.DEMO_PASSWORD,
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Скрыть пароль", exact: true })
    .click();
  await expect(password).toHaveAttribute("type", "password");
  await page
    .getByRole("button", { name: "Войти в кабинет", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();
});

test("native clipboard paste is accepted without suppressing paste events", async ({
  page,
  context,
  browserName,
}) => {
  test.skip(
    browserName !== "chromium" || process.platform === "darwin",
    "Native clipboard runs in isolated Linux Chromium; do not overwrite the user macOS clipboard",
  );
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/login");
  await page.evaluate((text) => navigator.clipboard.writeText(text), "client");
  await page.getByLabel("Логин", { exact: true }).focus();
  await page.keyboard.press("Control+V");
  await expect(page.getByLabel("Логин", { exact: true })).toHaveValue("client");
  await page.evaluate(
    (text) => navigator.clipboard.writeText(text),
    process.env.DEMO_PASSWORD!,
  );
  const password = page.getByLabel("Пароль", { exact: true });
  await password.focus();
  await page.keyboard.press("Control+V");
  expect(
    (await password.inputValue()) === process.env.DEMO_PASSWORD,
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Войти в кабинет", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();
});

test("an anonymous session check during login cannot invalidate the new session", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Логин", { exact: true }).fill("client");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  let releaseLogin = () => {};
  const loginHold = new Promise<void>((resolve) => {
    releaseLogin = resolve;
  });
  let loginStarted = () => {};
  const loginReady = new Promise<void>((resolve) => {
    loginStarted = resolve;
  });
  let releaseMe = () => {};
  const meHold = new Promise<void>((resolve) => {
    releaseMe = resolve;
  });
  let capturedAnonymous = false;
  await page.route("**/api/v1/session/login/", async (route) => {
    loginStarted();
    await loginHold;
    await route.continue();
  });
  await page.route("**/api/v1/me/", async (route) => {
    const response = await route.fetch();
    if (response.status() === 403) {
      capturedAnonymous = true;
      await meHold;
    }
    await route.fulfill({ response });
  });
  try {
    await page
      .getByRole("button", { name: "Войти в кабинет", exact: true })
      .click();
    await loginReady;
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    // Queue a browser task after focus: if /me was dispatched, finish it before login.
    // The fixed provider suppresses that redundant check while auth is in flight.
    await page.request.get("/api/v1/session/csrf/");
    releaseLogin();
    await expect(
      page.getByRole("heading", { name: /Здравствуйте/ }),
    ).toBeVisible();
    const delivered = capturedAnonymous
      ? page.waitForResponse("**/api/v1/me/")
      : null;
    releaseMe();
    if (delivered) await delivered;
    await page
      .getByRole("link", { name: "Заявки и кредиты", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Сессия требует входа" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Выйти из кабинета", exact: true }),
    ).toBeVisible();
  } finally {
    releaseLogin();
    releaseMe();
  }
});

test("password-manager values without change events are submitted exactly", async ({
  page,
}) => {
  await page.goto("/login");
  // Deliberately emulate a password manager writing native values, not ordinary typing.
  await page.getByLabel("Логин", { exact: true }).evaluate((input) => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, "client");
  });
  await page
    .getByLabel("Пароль", { exact: true })
    .evaluate((input, password) => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )!.set!.call(input, password);
    }, process.env.DEMO_PASSWORD!);
  await page
    .getByRole("button", { name: "Войти в кабинет", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /Здравствуйте/ }),
  ).toBeVisible();
});

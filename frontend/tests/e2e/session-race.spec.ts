import { test, expect } from "./fixtures";

test("a delayed pre-logout /me response cannot restore a previous user", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  let release: () => void = () => {};
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  try {
    await page.goto("/login");
    await page.getByLabel("Логин", { exact: true }).fill("client");
    await page
      .getByLabel("Пароль", { exact: true })
      .fill(process.env.DEMO_PASSWORD!);
    await page
      .getByRole("button", { name: "Войти в кабинет", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: /Здравствуйте/ }),
    ).toBeVisible();
    let captured: () => void = () => {};
    const intercepted = new Promise<void>((resolve) => {
      captured = resolve;
    });
    await page.route("**/api/v1/me/", async (route) => {
      const response = await route.fetch();
      captured();
      await hold;
      await route.fulfill({ response });
    });
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await intercepted;
    await page
      .getByRole("button", { name: "Выйти из кабинета", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Завершить сессию", exact: true })
      .click();
    await expect(page).toHaveURL(/\/login$/);
    const oldResponse = page.waitForResponse("**/api/v1/me/");
    release();
    await oldResponse;
    await expect(
      page.getByRole("button", { name: "Войти в кабинет", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Здравствуйте/ }),
    ).toHaveCount(0);
  } finally {
    release();
    await context.close();
  }
});

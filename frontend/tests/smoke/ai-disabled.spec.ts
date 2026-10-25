import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("AI disabled: no trigger or panel; login, form and review accessibility", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const accessible = async () =>
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations.map((v) => v.id),
    ).toEqual([]);
  await page.goto("/login");
  await expect(page.getByLabel("Логин", { exact: true })).toBeVisible();
  await accessible();
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
  await expect(
    page.getByRole("button", { name: "Савелий", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("dialog", { name: "Савелий, помощник по кредиту" }),
  ).toHaveCount(0);
  // Follow the actual app navigation instead of replacing the entire document.
  await page
    .getByRole("link")
    .filter({
      has: page.getByRole("heading", {
        name: "Оборотные средства · демо",
        exact: true,
      }),
    })
    .click();
  await expect(page.getByLabel("Цель кредита", { exact: true })).toBeVisible();
  await accessible();
  await page
    .getByRole("button", { name: "Проверить заявку", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Проверьте заявку", exact: true }),
  ).toBeVisible();
  await accessible();
  expect(errors).toEqual([]);
});

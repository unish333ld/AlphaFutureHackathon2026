import { test, expect, actor, create, showApp } from "./fixtures";

test("real queue pagination, typed search, native filters and own release", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    const initial = await (
      await staff.context.request.get("/api/v1/staff/applications/")
    ).json();
    for (let count = initial.count; count < 26; count++)
      await create(client.context);
    const app = await create(client.context);
    await staff.page.goto("/staff");
    await expect(
      staff.page.getByRole("button", {
        name: "Следующая страница",
        exact: true,
      }),
    ).toBeEnabled();
    await staff.page
      .getByRole("button", { name: "Следующая страница", exact: true })
      .click();
    await expect(staff.page).toHaveURL(/page=2/);
    await staff.page
      .getByLabel("Поиск по номеру, компании или ИНН", { exact: true })
      .fill(app.number);
    await expect(
      staff.page.getByRole("link", { name: app.number, exact: true }).first(),
    ).toBeVisible();
    await expect(staff.page).not.toHaveURL(/page=2/);
    await staff.page
      .getByRole("listbox", { name: "Статус", exact: true })
      .selectOption("review");
    await staff.page
      .getByRole("listbox", { name: "Риск", exact: true })
      .selectOption("low");
    await staff.page
      .getByRole("button", { name: "Свободные", exact: true })
      .click();
    await expect(
      staff.page.getByRole("link", { name: app.number, exact: true }).first(),
    ).toBeVisible();
    await showApp(staff.page, app, true);
    await staff.page
      .getByRole("button", { name: "Взять в работу", exact: true })
      .click();
    await expect(
      staff.page.getByRole("button", {
        name: "Освободить заявку",
        exact: true,
      }),
    ).toBeVisible();
    await staff.page
      .getByRole("button", { name: "Освободить заявку", exact: true })
      .click();
    await expect(
      staff.page.getByRole("button", { name: "Взять в работу", exact: true }),
    ).toBeEnabled();
    await expect(
      staff.page.getByRole("button", {
        name: "Принять решение по правилам",
        exact: true,
      }),
    ).toBeDisabled();
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

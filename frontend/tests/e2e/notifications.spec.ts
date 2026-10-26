import { test, expect, actor, create, post } from "./fixtures";

test("new decision appears once, pauses while focused and opens the right application @notifications", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    const baseline = client.page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/applications/notifications/") &&
        response.ok(),
    );
    await client.page.goto("/app");
    await baseline;
    await expect(client.page.locator('aside[role="status"]')).toHaveCount(0);

    let app = await create(client.context);
    app = await post(staff.context, `staff/applications/${app.id}/claim/`, {
      lock_version: app.lock_version,
    });
    await post(staff.context, `staff/applications/${app.id}/decide/`, {
      lock_version: app.lock_version,
    });

    const toast = client.page.locator('aside[role="status"]');
    await expect(toast).toBeVisible({ timeout: 12000 });
    await expect(toast).toContainText(app.number);
    await expect(toast).toContainText("Заявка одобрена");
    const link = toast.getByRole("link", { name: "Открыть заявку" });
    await link.focus();
    await expect(link).toBeFocused();
    await client.page.waitForTimeout(2400);
    await expect(toast).toBeVisible();
    await link.click();
    await expect(client.page).toHaveURL(new RegExp(`/app/loans/${app.id}$`));
    await expect(
      client.page.getByRole("heading", { name: `Заявка ${app.number}` }),
    ).toBeVisible();
    await expect(toast).toHaveCount(0);
    let second = await create(client.context);
    second = await post(
      staff.context,
      `staff/applications/${second.id}/claim/`,
      { lock_version: second.lock_version },
    );
    await post(
      staff.context,
      `staff/applications/${second.id}/request-information/`,
      {
        lock_version: second.lock_version,
        question: "Проверьте месячную выручку.",
      },
    );
    await expect(toast).toBeVisible({ timeout: 12000 });
    await expect(toast).toContainText("Проверьте данные заявки");
    await toast.hover();
    await client.page.waitForTimeout(2400);
    await expect(toast).toBeVisible();
    await client.page.mouse.move(0, 0);
    await client.page.waitForTimeout(1000);
    await expect(toast).toBeVisible();
    await expect(toast).toHaveCount(0);
    await client.page.reload();
    await client.page.waitForTimeout(6000);
    await expect(client.page.locator('aside[role="status"]')).toHaveCount(0);
    // Stop the scheduled request before WebKit tears down its fetch context.
    await client.page.goto("about:blank");
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

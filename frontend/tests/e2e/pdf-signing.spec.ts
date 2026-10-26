import AxeBuilder from "@axe-core/playwright";
import { test, expect, actor, decide, post, getApp, showApp } from "./fixtures";
import { currentOffer } from "../../src/entities/credit";
import type { Page } from "@playwright/test";

test.use({ trace: "off" }); // Never persist the one-time code in a network trace.

test("mobile review remains accessible when embedded PDF is unavailable @pdf", async ({
  browser,
  sessions,
  baseURL,
}, info) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    let app = await decide(client.context, staff.context);
    app = await post(
      client.context,
      `offers/${currentOffer(app)!.id}/accept/`,
      {
        lock_version: app.lock_version,
      },
    );
    await client.page.setViewportSize({ width: 360, height: 800 });
    await client.page.emulateMedia({ reducedMotion: "reduce" });
    await showApp(client.page, app);
    await client.page
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const dialog = client.page.getByRole("dialog", {
      name: "Просмотр договора",
      exact: true,
    });
    await dialog.getByRole("checkbox").focus();
    await expect(dialog.getByRole("checkbox")).toBeFocused();
    await expect(
      dialog.getByRole("button", { name: "Подписать договор", exact: true }),
    ).toBeDisabled();
    // Fault injection only for the optional frame; the authorized download remains real.
    await client.page.route("**/pdf/?kind=original", async (route) => {
      if (route.request().isNavigationRequest())
        await route.fulfill({
          status: 503,
          contentType: "text/plain",
          body: "Просмотр временно недоступен",
        });
      else await route.continue();
    });
    await dialog
      .getByRole("button", { name: "Встроенный просмотр PDF", exact: true })
      .click();
    await expect(
      dialog.getByText(/Если браузер не поддерживает просмотр PDF/),
    ).toBeVisible();
    const download = client.page.waitForEvent("download");
    await dialog
      .getByRole("link", {
        name: "Скачать исходный договор (PDF)",
        exact: true,
      })
      .click();
    expect((await download).suggestedFilename()).toMatch(/-original\.pdf$/);
    expect(
      await client.page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(
      await dialog.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
    const axe = await new AxeBuilder({ page: client.page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      axe.violations.map((item) => ({
        id: item.id,
        targets: item.nodes.map((node) => node.target),
      })),
    ).toEqual([]);
    await client.page.screenshot({
      path: info.outputPath("review-mobile-360.png"),
      fullPage: true,
    });
    await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(
      client.page.getByRole("link", {
        name: "Скачать исходный договор (PDF)",
        exact: true,
      }),
    ).toBeVisible();
    expect((await getApp(client.context, app.id)).status).toBe("accepted");
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

async function review(page: Page) {
  await page
    .getByRole("button", { name: "Подписать договор", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Просмотр договора",
    exact: true,
  });
  await expect(
    dialog.getByRole("button", { name: "Подписать договор", exact: true }),
  ).toBeDisabled();
  await dialog.getByRole("checkbox").press("Space");
  return dialog;
}

test("PDF download, cancel before code, reopen, double click, signature and specialist issuance @pdf", async ({
  browser,
  sessions,
  baseURL,
}, info) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    let app = await decide(client.context, staff.context);
    app = await post(
      client.context,
      `offers/${currentOffer(app)!.id}/accept/`,
      { lock_version: app.lock_version },
    );
    await showApp(client.page, app);
    await client.page.clock.install({ time: new Date("2026-10-26T08:00:00Z") });
    await client.page.clock.pauseAt(new Date("2026-10-26T08:00:00.100Z"));
    let signs = 0;
    client.page.on("request", (request) => {
      if (request.method() === "POST" && request.url().endsWith("/sign/"))
        signs++;
    });
    let dialog = await review(client.page);
    const downloaded = client.page.waitForEvent("download");
    await dialog
      .getByRole("link", {
        name: "Скачать исходный договор (PDF)",
        exact: true,
      })
      .click();
    const download = await downloaded;
    expect(download.suggestedFilename()).toMatch(
      /^agreement-.*-v1-original\.pdf$/,
    );
    await download.saveAs(info.outputPath("downloaded-original.pdf"));
    await dialog
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const confirmation = client.page.getByRole("dialog", {
      name: "Подтверждение подписания",
      exact: true,
    });
    await expect(confirmation.getByLabel("Шестизначный демо-код")).toBeEmpty();
    await confirmation
      .getByRole("button", { name: "Отмена", exact: true })
      .click();
    await client.page.clock.runFor(1500);
    expect(signs).toBe(0);
    expect((await getApp(client.context, app.id)).status).toBe("accepted");
    dialog = await review(client.page);
    await dialog
      .getByRole("button", { name: "Подписать договор", exact: true })
      .evaluate((element) => {
        (element as HTMLButtonElement).click();
        (element as HTMLButtonElement).click();
      });
    await expect(confirmation).toBeVisible();
    await client.page.clock.runFor(1001);
    const success = client.page.getByRole("dialog", {
      name: "Договор подписан в демо-режиме",
      exact: true,
    });
    await expect(success).toBeVisible();
    expect(signs).toBe(1);
    app = await getApp(client.context, app.id);
    expect(app.status).toBe("signed");
    expect(currentOffer(app)!.agreement!.disbursement).toBeNull();
    await client.page.clock.runFor(3000);
    await expect(success).toHaveCount(0);
    await expect(
      client.page.getByText(
        "Условная подпись сохранена. Ожидается моделируемая выдача специалистом.",
        { exact: true },
      ),
    ).toBeVisible();
    const agreement = currentOffer(app)!.agreement!;
    const pdf = await client.context.request.get(
      `/api/v1/agreements/${agreement.id}/pdf/`,
    );
    expect(pdf.headers()["content-type"]).toBe("application/pdf");
    const originalBytes = await pdf.body();
    await post(
      staff.context,
      `agreements/${agreement.id}/disburse/`,
      { lock_version: app.lock_version },
      crypto.randomUUID(),
    );
    const updated = client.page.waitForResponse(
      (response) =>
        response.url().endsWith(`/applications/${app.id}/`) &&
        response.request().method() === "GET",
    );
    await client.page
      .getByRole("button", { name: "Обновить карточку", exact: true })
      .click();
    await (await updated).json();
    // TanStack Query batches notifications on a timer; flush the paused clock.
    await client.page.clock.runFor(50);
    const issued = client.page.getByRole("dialog", {
      name: "Демо-выдача завершена",
      exact: true,
    });
    await expect(issued).toBeVisible();
    await expect(issued).toContainText("Реального перевода денег не было");
    await issued.getByRole("button", { name: "Закрыть", exact: true }).focus();
    await client.page.clock.runFor(4000);
    await expect(issued).toBeVisible();
    await issued.getByRole("button", { name: "Закрыть", exact: true }).click();
    await client.page.clock.runFor(500); // Complete Core Modal's exit transition.
    await expect(issued).toHaveCount(0);
    await client.page.clock.resume();
    await client.page
      .getByRole("button", { name: "Обновить карточку", exact: true })
      .click();
    await expect(issued).toHaveCount(0);
    const reread = await client.context.request.get(
      `/api/v1/agreements/${agreement.id}/pdf/`,
    );
    expect(await reread.body()).toEqual(originalBytes);
    await client.page.reload();
    await expect(client.page.getByRole("dialog")).toHaveCount(0);
    for (const width of [360, 768, 1280, 1440]) {
      await client.page.setViewportSize({ width, height: 900 });
      expect(
        await client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    const axe = await new AxeBuilder({ page: client.page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(axe.violations.map((item) => item.id)).toEqual([]);
    await client.page.screenshot({
      path: info.outputPath("issued-1440.png"),
      fullPage: true,
    });
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("navigation before code prevents sign; reload and lost sign response reconcile without another POST @pdf", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    let app = await decide(client.context, staff.context);
    app = await post(
      client.context,
      `offers/${currentOffer(app)!.id}/accept/`,
      { lock_version: app.lock_version },
    );
    await showApp(client.page, app);
    await client.page.clock.install({ time: new Date("2026-10-26T08:00:00Z") });
    await client.page.clock.pauseAt(new Date("2026-10-26T08:00:00.100Z"));
    const dialog = await review(client.page);
    await dialog
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    await expect(
      client.page.getByRole("dialog", {
        name: "Подтверждение подписания",
        exact: true,
      }),
    ).toBeVisible();
    await client.page.goto("/app/loans");
    await client.page.clock.runFor(2000);
    expect((await getApp(client.context, app.id)).status).toBe("accepted");
    await client.page.clock.resume();
    // Return through the actual SPA link, not a second document replacement
    // while list detail requests are starting (WebKit engine issue #43120).
    await client.page
      .getByRole("link", { name: new RegExp(app.number) })
      .click();
    await expect(
      client.page.getByRole("heading", {
        name: `Заявка ${app.number}`,
        exact: true,
      }),
    ).toBeVisible();
    await client.page.clock.pauseAt(new Date("2026-10-26T08:00:05Z"));
    let signs = 0;
    await client.page.route("**/sign/", async (route) => {
      signs++;
      const result = await route.fetch().catch(() => null);
      if (result?.ok()) await route.abort("connectionfailed");
      else
        await route.fulfill({
          status: 503,
          json: { detail: "Неопределённый результат" },
        });
    });
    const second = await review(client.page);
    await second
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    await expect(
      client.page.getByRole("dialog", {
        name: "Подтверждение подписания",
        exact: true,
      }),
    ).toBeVisible();
    await client.page.clock.runFor(1001);
    const success = client.page.getByRole("dialog", {
      name: "Договор подписан в демо-режиме",
      exact: true,
    });
    await expect(success).toBeVisible();
    expect(signs).toBe(1);
    expect((await getApp(client.context, app.id)).status).toBe("signed");
    await client.page.clock.resume();
    await client.page.reload();
    await expect(
      client.page.getByRole("heading", {
        name: `Заявка ${app.number}`,
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      client.page.getByText(
        "Условная подпись сохранена. Ожидается моделируемая выдача специалистом.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      client.page.getByRole("button", {
        name: "Подписать договор",
        exact: true,
      }),
    ).toHaveCount(0);
    expect(signs).toBe(1);
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("server failure after code is visible, does not sign or issue, and never retries automatically @pdf", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    let app = await decide(client.context, staff.context);
    app = await post(
      client.context,
      `offers/${currentOffer(app)!.id}/accept/`,
      { lock_version: app.lock_version },
    );
    await showApp(client.page, app);
    let signs = 0;
    await client.page.route("**/sign/", (route) => {
      signs++;
      return route.fulfill({
        status: 503,
        json: { detail: "Временная ошибка подтверждения" },
      });
    });
    const dialog = await review(client.page);
    await dialog
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const confirmation = client.page.getByRole("dialog", {
      name: "Подтверждение подписания",
      exact: true,
    });
    await expect(confirmation.getByRole("alert")).toBeVisible();
    await expect(confirmation).toContainText(
      "Автоматического повтора не будет",
    );
    expect(signs).toBe(1);
    const saved = await getApp(client.context, app.id);
    expect(saved.status).toBe("accepted");
    expect(currentOffer(saved)!.agreement!.signed_at).toBeNull();
    expect(currentOffer(saved)!.agreement!.disbursement).toBeNull();
    await confirmation
      .getByRole("button", { name: "Закрыть", exact: true })
      .click();
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

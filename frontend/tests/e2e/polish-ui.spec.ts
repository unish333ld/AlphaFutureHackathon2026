import AxeBuilder from "@axe-core/playwright";
import { test, expect, actor, post, showApp, signed } from "./fixtures";
import { currentOffer } from "../../src/entities/credit";

test("profile uses the current account and layouts fit five viewport widths @polish-ui", async ({
  browser,
  sessions,
  baseURL,
}, info) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    const user = await (await client.context.request.get("/api/v1/me/")).json();
    await client.page.goto("/app");
    for (const width of [360, 390, 768, 1024, 1440]) {
      await client.page.setViewportSize({ width, height: 900 });
      const profile = client.page.getByRole("button", { name: /^Профиль:/ });
      await expect(profile).toBeVisible();
      if (width <= 600) await expect(profile).toContainText("Профиль");
      await expect(
        client.page.getByRole("button", {
          name: "Выйти из кабинета",
          exact: true,
        }),
      ).toBeVisible();
      expect(
        await client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await client.page.evaluate(() => window.scrollTo(0, 0));
      await client.page.screenshot({
        path: info.outputPath(`home-${width}.png`),
        fullPage: true,
      });
      if (width === 768) {
        const launcher = await client.page
          .getByRole("button", { name: "Помощник по кредиту", exact: true })
          .boundingBox();
        const allApplications = await client.page
          .getByRole("link", { name: /Все заявки/ })
          .boundingBox();
        expect(launcher && allApplications).toBeTruthy();
        expect(
          launcher!.x < allApplications!.x + allApplications!.width &&
            launcher!.x + launcher!.width > allApplications!.x &&
            launcher!.y < allApplications!.y + allApplications!.height &&
            launcher!.y + launcher!.height > allApplications!.y,
        ).toBe(false);
      }
      await profile.focus();
      await client.page.keyboard.press("Enter");
      const dialog = client.page.getByRole("dialog", {
        name: "Профиль",
        exact: true,
      });
      await expect(dialog).toContainText(user.username);
      await expect(dialog.getByRole("textbox")).toHaveCount(0);
      await expect(dialog).toContainText("ИНН");
      await dialog.evaluate(async (element) => {
        await Promise.all(
          element
            .getAnimations({ subtree: true })
            .map((animation) => animation.finished.catch(() => undefined)),
        );
      });
      await expect
        .poll(() =>
          dialog.evaluate((element) => {
            const visibleText = [
              element,
              ...element.querySelectorAll("*"),
            ].filter(
              (node) =>
                node.textContent?.trim() &&
                node.getBoundingClientRect().width > 0 &&
                node.getBoundingClientRect().height > 0,
            );
            return Math.min(
              ...visibleText.map((textNode) => {
                let opacity = 1;
                for (
                  let node: Element | null = textNode;
                  node;
                  node = node.parentElement
                )
                  opacity *= Number(getComputedStyle(node).opacity);
                return opacity;
              }),
            );
          }),
        )
        .toBe(1);
      expect(
        await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth),
      ).toBe(true);
      await client.page.screenshot({
        path: info.outputPath(`profile-${width}.png`),
      });
      if (width === 360 || width === 1440) {
        const accessibility = await new AxeBuilder({ page: client.page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        expect(
          accessibility.violations.map((value) => ({
            id: value.id,
            nodes: value.nodes.map((node) => node.target),
          })),
        ).toEqual([]);
      }
      await client.page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(profile).toBeFocused();
      await staff.page.setViewportSize({ width, height: 900 });
      await staff.page.goto("/staff");
      await expect(
        staff.page.getByRole("heading", {
          name: "Очередь заявок",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        staff.page.getByLabel("Поиск по номеру, компании или ИНН", {
          exact: true,
        }),
      ).toBeVisible();
      expect(
        await staff.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await staff.page.screenshot({
        path: info.outputPath(`queue-${width}.png`),
        fullPage: true,
      });
    }
    // A 720 CSS-pixel viewport checks the reflow available at 200% on a 1440-pixel screen.
    await client.page.setViewportSize({ width: 720, height: 450 });
    expect(
      await client.page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await client.page.getByRole("button", { name: /^Профиль:/ }).click();
    await expect(
      client.page.getByRole("dialog", { name: "Профиль", exact: true }),
    ).toBeVisible();
    await client.page.screenshot({
      path: info.outputPath("profile-200-percent-reflow.png"),
    });
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("history requests pages of ten and retains its page after an external action @polish-ui", async ({
  browser,
  sessions,
  baseURL,
}, info) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    let app = await post(client.context, "applications/", {
      company: "00000000-0000-0000-0000-000000000001",
      product: "00000000-0000-0000-0000-000000000065",
      amount: "1100000.00",
      term_months: 24,
      purpose: "Закупка материалов для сезонного производства",
      monthly_revenue: "1500000.00",
      monthly_expenses: "900000.00",
      monthly_debt_payments: "50000.00",
    });
    const token = (
      await (await client.context.request.get("/api/v1/session/csrf/")).json()
    ).csrf_token;
    for (let revision = 1; revision <= 20; revision++) {
      const updated = await client.context.request.patch(
        `/api/v1/applications/${app.id}/`,
        {
          headers: { "X-CSRFToken": token },
          data: {
            lock_version: app.lock_version,
            purpose: `Закупка материалов для сезонного производства, этап ${revision}`,
          },
        },
      );
      expect(updated.ok()).toBe(true);
      app = await updated.json();
    }
    app = await post(client.context, `applications/${app.id}/submit/`, {
      lock_version: app.lock_version,
    });
    await showApp(client.page, app);
    const history = client.page
      .getByRole("heading", { name: "История заявки", exact: true })
      .locator("xpath=ancestor::section[1]");
    await expect(history.locator("ol > li")).toHaveCount(10);
    const next = client.page.waitForResponse(
      (response) =>
        response.url().includes(`/applications/${app.id}/events/?page=2`) &&
        response.ok(),
    );
    await history
      .getByRole("button", { name: "Следующая страница", exact: true })
      .click();
    const second = await (await next).json();
    expect(second.results).toHaveLength(10);
    await expect(history).toContainText(`11–20 из ${second.count}`);
    await post(staff.context, `staff/applications/${app.id}/claim/`, {
      lock_version: app.lock_version,
    });
    await expect(history).toContainText(`11–20 из ${second.count + 1}`, {
      timeout: 12000,
    });
    await expect(history.locator("ol > li")).toHaveCount(10);
    await history
      .getByRole("button", { name: "Следующая страница", exact: true })
      .click();
    await expect(history).toContainText(
      `21–${second.count + 1} из ${second.count + 1}`,
    );
    await expect(
      history.getByRole("button", { name: "Следующая страница", exact: true }),
    ).toBeDisabled();
    for (const width of [360, 390, 768, 1024, 1440]) {
      await client.page.setViewportSize({ width, height: 900 });
      expect(
        await client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await client.page.evaluate(() => window.scrollTo(0, 0));
      await client.page.screenshot({
        path: info.outputPath(`application-${width}.png`),
        fullPage: true,
      });
    }
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("the client list refreshes an externally issued agreement without a refresh button @polish-ui", async ({
  browser,
  sessions,
  baseURL,
}) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  const staff = await actor(browser, sessions, "specialist", baseURL!);
  try {
    const app = await signed(client.context, staff.context);
    await client.page.goto("/app/loans");
    const row = client.page.getByRole("link", { name: new RegExp(app.number) });
    await expect(
      row.getByText("Договор подписан", { exact: true }),
    ).toBeVisible();
    await post(
      staff.context,
      `agreements/${currentOffer(app)!.agreement!.id}/disburse/`,
      { lock_version: app.lock_version },
      crypto.randomUUID(),
    );
    await expect(
      row.getByText("Выдача завершена", { exact: true }),
    ).toBeVisible({ timeout: 15000 });
    await expect(
      client.page.getByRole("button", {
        name: "Обновить карточку",
        exact: true,
      }),
    ).toHaveCount(0);
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

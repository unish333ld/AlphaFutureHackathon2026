import AxeBuilder from "@axe-core/playwright";
import { test, expect, actor, post, getApp, showApp } from "./fixtures";
import { currentOffer, money } from "../../src/entities/credit";
import type { Schema } from "../../src/shared/api/client";

test("readiness field focus, server-priced quote, evidence and responsive cost @product-research", async ({
  browser,
  sessions,
  baseURL,
}, info) => {
  const client = await actor(browser, sessions, "client", baseURL!);
  try {
    await client.page.goto(
      "/app/loans/new?company=00000000-0000-0000-0000-000000000001&product=00000000-0000-0000-0000-000000000065",
    );
    await client.page
      .getByRole("button", { name: "Проверить: Месячная выручка", exact: true })
      .click();
    const revenue = client.page.getByLabel("Месячная выручка, ₽", {
      exact: true,
    });
    await expect(revenue).toBeFocused();
    await revenue.fill("1500000");
    await client.page
      .getByLabel("Месячные расходы, ₽", { exact: true })
      .fill("900000");
    await client.page
      .getByLabel("Месячные платежи по обязательствам, ₽", { exact: true })
      .fill("0");
    await expect(
      client.page.getByText(
        "Указано 3 из 3 показателей. Заполненность не означает одобрение.",
      ),
    ).toBeVisible();
    const response = client.page.waitForResponse(
      (item) =>
        item.url().includes("/calculator/payment/") &&
        item.request().method() === "POST",
    );
    await client.page
      .getByRole("button", { name: "Рассчитать платёж", exact: true })
      .click();
    const result = await response;
    expect(result.status()).toBe(200);
    const quote = (await result.json()) as Schema["PaymentResponse"];
    expect(quote.annual_rate).toBe("27.0000");
    expect(quote.rate_source).toBe("demo_assumption");
    const cost = client.page.getByRole("region", {
      name: "Стоимость кредита",
      exact: true,
    });
    await expect(cost).toContainText(
      money(quote.cost_breakdown.total_repayment),
    );
    await expect(
      client.page.getByText("Откуда взяты условия", { exact: true }),
    ).toHaveCount(0);
    await expect(
      client.page.getByRole("link", {
        name: "Альфа-Банк: кредит одной суммой без залога",
      }),
    ).toHaveCount(0);
    for (const width of [360, 390, 768, 1024, 1440]) {
      await client.page.setViewportSize({ width, height: 900 });
      expect(
        await client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width === 360 || width === 1440) {
        const result = await new AxeBuilder({ page: client.page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        expect(result.violations.map((v) => v.id)).toEqual([]);
        await client.page.screenshot({
          path: info.outputPath(`quote-${width}.png`),
          fullPage: true,
        });
      }
    }
    await client.page.getByLabel("Сумма, ₽", { exact: true }).fill("1200000");
    await expect(cost).toHaveCount(0);
    await expect(revenue).toHaveValue("1500000");
  } finally {
    await client.context.close();
  }
});

test("counteroffer comparison and signed price passport survive acceptance and issuance @product-research", async ({
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
      amount: "1500000.00",
      term_months: 24,
      purpose: "Закупка товара для тестового сценария",
      monthly_revenue: "500000.00",
      monthly_expenses: "320000.00",
      monthly_debt_payments: "30000.00",
    });
    app = await post(client.context, `applications/${app.id}/submit/`, {
      lock_version: app.lock_version,
    });
    app = await post(staff.context, `staff/applications/${app.id}/claim/`, {
      lock_version: app.lock_version,
    });
    app = await post(staff.context, `staff/applications/${app.id}/decide/`, {
      lock_version: app.lock_version,
    });
    const offer = currentOffer(app)!;
    expect(offer.comparison.requested.monthly_payment).toBe("81570.34");
    await showApp(client.page, app);
    const comparison = client.page.getByRole("region", {
      name: "Сравнение условий",
      exact: true,
    });
    await expect(comparison).toContainText(money("1500000.00"));
    await expect(comparison).toContainText(money(offer.amount));
    for (const width of [360, 768, 1280, 1440]) {
      await client.page.setViewportSize({ width, height: 900 });
      expect(
        await client.page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await client.page.screenshot({
      path: info.outputPath("counteroffer-1440.png"),
      fullPage: true,
    });
    await client.page
      .getByRole("button", { name: "Принять предложение", exact: true })
      .click();
    const accept = client.page.getByRole("dialog", {
      name: "Принять предложение",
      exact: true,
    });
    await expect(accept).toContainText(
      money(offer.cost_breakdown.total_repayment),
    );
    await accept
      .getByRole("button", { name: "Подтвердить", exact: true })
      .click();
    await expect(accept).toHaveCount(0);
    await client.page
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const sign = client.page.getByRole("dialog", {
      name: "Просмотр договора",
      exact: true,
    });
    await expect(sign).toContainText(
      money(offer.cost_breakdown.total_repayment),
    );
    await sign.getByRole("checkbox").press("Space");
    await sign
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    await expect(sign).toHaveCount(0);
    const signed = client.page.getByRole("dialog", {
      name: "Договор подписан в демо-режиме",
      exact: true,
    });
    await expect(signed).toBeVisible();
    await signed.getByRole("button", { name: "Закрыть", exact: true }).click();
    app = await getApp(client.context, app.id);
    expect(app.status).toBe("signed");
    const agreement = currentOffer(app)!.agreement!;
    expect(agreement.cost_breakdown).toEqual(offer.cost_breakdown);
    await post(
      staff.context,
      `agreements/${agreement.id}/disburse/`,
      { lock_version: app.lock_version },
      crypto.randomUUID(),
    );
    await client.page.reload();
    await expect(
      client.page.getByText("Выдача завершена", { exact: true }).first(),
    ).toBeVisible();
    app = await getApp(client.context, app.id);
    expect(currentOffer(app)!.agreement!.cost_breakdown).toEqual(
      offer.cost_breakdown,
    );
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

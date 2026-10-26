import {
  test as base,
  expect,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import type { Application, Schema } from "../../src/shared/api/client";
import { currentOffer } from "../../src/entities/credit";
import { chmodSync, existsSync, mkdirSync, readFileSync } from "node:fs";

export const test = base.extend<{}, { sessions: Record<string, unknown> }>({
  sessions: [
    async ({ browser }, use) => {
      const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080";
      if (!process.env.DEMO_PASSWORD)
        throw new Error(
          "Set DEMO_PASSWORD for the isolated synthetic E2E database",
        );
      const sessions: Record<string, unknown> = {};
      for (const username of [
        "client",
        "specialist",
        "e2e-specialist",
        "outsider",
        "accountant",
      ]) {
        const context = await browser.newContext({ baseURL });
        mkdirSync(".auth", { recursive: true, mode: 0o700 });
        const statePath = `.auth/${new URL(baseURL).port}-${username}.json`;
        if (existsSync(statePath)) {
          const stored = JSON.parse(readFileSync(statePath, "utf8"));
          await context.addCookies(stored.cookies);
          const me = await context.request.get("/api/v1/me/");
          if (me.ok() && (await me.json()).username === username) {
            sessions[username] = stored;
            await context.close();
            continue;
          }
          await context.clearCookies();
        }
        const csrf = await context.request.get("/api/v1/session/csrf/");
        expect(csrf.ok()).toBeTruthy();
        const loginRequest = async () =>
          context.request.post("/api/v1/session/login/", {
            data: { username, password: process.env.DEMO_PASSWORD },
            headers: {
              "X-CSRFToken": (await csrf.json()).csrf_token,
              Origin: baseURL!,
            },
          });
        let login = await loginRequest();
        if (login.status() === 429) {
          await new Promise((resolve) =>
            setTimeout(
              resolve,
              Math.min(60, Number(login.headers()["retry-after"]) || 60) * 1000,
            ),
          );
          login = await loginRequest();
        }
        expect(login.ok(), `session login: ${username}`).toBeTruthy();
        sessions[username] = await context.storageState({ path: statePath });
        chmodSync(statePath, 0o600);
        await context.close();
      }
      await use(sessions);
    },
    { scope: "worker", timeout: 180000 },
  ],
});
export { expect };
export async function actor(
  browser: Browser,
  sessions: Record<string, unknown>,
  username: string,
  baseURL: string,
) {
  const context = await browser.newContext({
    baseURL,
    storageState: sessions[username] as Awaited<
      ReturnType<BrowserContext["storageState"]>
    >,
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => {
    throw error;
  });
  return { context, page };
}
export async function post<T = Application>(
  context: BrowserContext,
  path: string,
  data: unknown,
  key?: string,
): Promise<T> {
  const csrf = await context.request.get("/api/v1/session/csrf/");
  const response = await context.request.post(`/api/v1/${path}`, {
    data,
    headers: {
      "X-CSRFToken": (await csrf.json()).csrf_token,
      ...(key ? { "Idempotency-Key": key } : {}),
    },
  });
  expect(
    response.ok(),
    `${path}: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return response.json();
}
export async function getApp(
  context: BrowserContext,
  id: string,
): Promise<Application> {
  const response = await context.request.get(`/api/v1/applications/${id}/`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}
export async function create(
  context: BrowserContext,
  options: {
    company?: number;
    revenue?: string | null;
    expenses?: string | null;
    debt?: string | null;
    purpose?: string;
  } = {},
) {
  const app = await post(context, "applications/", {
    company: `00000000-0000-0000-0000-${String(options.company ?? 1).padStart(12, "0")}`,
    product: "00000000-0000-0000-0000-000000000065",
    amount: "1000000.00",
    term_months: 24,
    purpose: options.purpose ?? `E2E ${crypto.randomUUID()}`,
    monthly_revenue:
      options.revenue === undefined ? "1500000.00" : options.revenue,
    monthly_expenses:
      options.expenses === undefined ? "900000.00" : options.expenses,
    monthly_debt_payments:
      options.debt === undefined ? "50000.00" : options.debt,
  });
  return post(context, `applications/${app.id}/submit/`, {
    lock_version: app.lock_version,
  });
}
export async function decide(
  client: BrowserContext,
  staff: BrowserContext,
  options: Parameters<typeof create>[1] = {},
) {
  let app = await create(client, options);
  app = await post(staff, `staff/applications/${app.id}/claim/`, {
    lock_version: app.lock_version,
  });
  return post(staff, `staff/applications/${app.id}/decide/`, {
    lock_version: app.lock_version,
  });
}
export async function signed(client: BrowserContext, staff: BrowserContext) {
  let app = await decide(client, staff);
  const offer = currentOffer(app)!;
  app = await post(client, `offers/${offer.id}/accept/`, {
    lock_version: app.lock_version,
  });
  await signWithDemoCode(client, app);
  return getApp(client, app.id);
}
export async function signWithDemoCode(
  client: BrowserContext,
  app: Application,
) {
  const agreement = currentOffer(app)!.agreement!;
  const document = await post<Schema["AgreementDocument"]>(
    client,
    `agreements/${agreement.id}/generate-document/`,
    { lock_version: app.lock_version, document_hash: agreement.document_hash },
  );
  const attempt = await post<Schema["SignatureAttempt"]>(
    client,
    `agreements/${agreement.id}/signature-attempt/`,
    {
      lock_version: app.lock_version,
      document_hash: agreement.document_hash,
      document_id: document.id,
      pdf_sha256: document.pdf_sha256,
      acknowledged: true,
      confirm_simulation: true,
    },
  );
  await post<Schema["Agreement"]>(client, `agreements/${agreement.id}/sign/`, {
    lock_version: app.lock_version,
    document_hash: agreement.document_hash,
    confirm_simulation: true,
    document_id: document.id,
    pdf_sha256: document.pdf_sha256,
    attempt_id: attempt.id,
    code: attempt.demo_code,
  });
}
export async function uiSign(page: Page) {
  await page
    .getByRole("button", { name: "Подписать договор", exact: true })
    .click();
  const review = page.getByRole("dialog", {
    name: "Просмотр договора",
    exact: true,
  });
  await expect(
    review.getByRole("button", { name: "Подписать договор", exact: true }),
  ).toBeDisabled();
  await review.getByRole("checkbox").press("Space");
  await review
    .getByRole("button", { name: "Подписать договор", exact: true })
    .click();
  const success = page.getByRole("dialog", {
    name: "Договор подписан в демо-режиме",
    exact: true,
  });
  await expect(success).toBeVisible();
  await expect(success).toContainText(
    "Ожидается моделируемая выдача специалистом",
  );
  await success.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(success).toHaveCount(0);
}
export async function showApp(page: Page, app: Application, staff = false) {
  await page.goto(`${staff ? "/staff/applications/" : "/app/loans/"}${app.id}`);
  await expect(
    page.getByRole("heading", { name: `Заявка ${app.number}`, exact: true }),
  ).toBeVisible();
}
export async function uiAction(
  page: Page,
  name: string,
  confirm = "Подтвердить",
) {
  await page.getByRole("button", { name, exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: name === "Повторить с тем же ключом" ? "Моделировать выдачу" : name,
    exact: true,
  });
  await dialog.getByRole("button", { name: confirm, exact: true }).click();
  await expect(dialog).toHaveCount(0);
}

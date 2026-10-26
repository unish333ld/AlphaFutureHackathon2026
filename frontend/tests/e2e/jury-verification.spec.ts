import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import {
  test,
  expect,
  actor,
  decide,
  getApp,
  showApp,
  uiAction,
  post,
} from "./fixtures";
import { currentOffer } from "../../src/entities/credit";

test.use({ trace: "off" });

test("jury: signed copy failure is recoverable without another signature @jury", async ({
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
    client.page.on("request", (request) => {
      if (request.method() === "POST" && request.url().endsWith("/sign/"))
        signs++;
    });
    await client.page.route("**/signed-document/", (route) =>
      route.fulfill({
        status: 503,
        json: { detail: "Копия временно недоступна" },
      }),
    );
    const copyFailure = client.page.waitForResponse(
      (response) =>
        response.url().endsWith("/signed-document/") &&
        response.status() === 503,
    );
    await client.page
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const review = client.page.getByRole("dialog", {
      name: "Просмотр договора",
      exact: true,
    });
    await review.getByRole("checkbox").press("Space");
    await review
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const success = client.page.getByRole("dialog", {
      name: "Договор подписан в демо-режиме",
      exact: true,
    });
    await expect(success).toBeVisible();
    await success.getByRole("button", { name: "Закрыть", exact: true }).click();
    const retry = client.page.getByRole("button", {
      name: "Сформировать копию с демо-отметкой",
      exact: true,
    });
    await expect(retry).toBeVisible();
    await copyFailure;
    app = await getApp(client.context, app.id);
    expect(app.status).toBe("signed");
    const agreement = currentOffer(app)!.agreement!;
    expect(agreement.disbursement).toBeNull();
    const original = await client.context.request.get(
      `/api/v1/agreements/${agreement.id}/pdf/`,
    );
    const bytes = await original.body();
    await client.page.unroute("**/signed-document/");
    let copyRequests = 0;
    client.page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/signed-document/")
      )
        copyRequests++;
    });
    await retry.evaluate((element) => {
      (element as HTMLButtonElement).click();
      (element as HTMLButtonElement).click();
    });
    await expect(
      client.page.getByRole("link", {
        name: "Скачать копию с демо-отметкой (PDF)",
        exact: true,
      }),
    ).toBeVisible();
    expect(copyRequests).toBe(1);
    const reread = await client.context.request.get(
      `/api/v1/agreements/${agreement.id}/pdf/`,
    );
    expect(await reread.body()).toEqual(bytes);
    expect(signs).toBe(1);
    const final = currentOffer(
      await getApp(client.context, app.id),
    )!.agreement!;
    expect(final.confirmation!.id).toBe(agreement.confirmation!.id);
    expect(final.disbursement).toBeNull();
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

test("jury: confirmed signature stays acknowledged if subsequent card reads fail @jury", async ({
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
    let blockReads = false;
    let signs = 0;
    await client.page.route(`**/applications/${app.id}/`, async (route) => {
      if (blockReads && route.request().method() === "GET")
        await route.fulfill({
          status: 503,
          json: { detail: "Обновление карточки недоступно" },
        });
      else await route.continue();
    });
    await client.page.route("**/sign/", async (route) => {
      signs++;
      const result = await route.fetch();
      expect(result.ok()).toBe(true);
      blockReads = true;
      await route.fulfill({ response: result });
    });
    await client.page
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const review = client.page.getByRole("dialog", {
      name: "Просмотр договора",
      exact: true,
    });
    await review.getByRole("checkbox").press("Space");
    await review
      .getByRole("button", { name: "Подписать договор", exact: true })
      .click();
    const success = client.page.getByRole("dialog", {
      name: "Договор подписан в демо-режиме",
      exact: true,
    });
    await expect(success).toBeVisible();
    await success.getByRole("button", { name: "Закрыть", exact: true }).click();
    expect((await getApp(client.context, app.id)).status).toBe("signed");
    await expect(
      client.page.getByRole("button", {
        name: "Подписать договор",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(
      client.page.getByText(/Сервер подтвердил подпись/),
    ).toBeVisible();
    blockReads = false;
    await client.page
      .getByRole("button", { name: "Обновить карточку", exact: true })
      .click();
    await expect(
      client.page.getByText(
        "Условная подпись сохранена. Ожидается моделируемая выдача специалистом.",
        { exact: true },
      ),
    ).toBeVisible();
    expect(signs).toBe(1);
  } finally {
    await client.context.close();
    await staff.context.close();
  }
});

for (const outcome of ["approved", "counteroffer"] as const) {
  test(`jury: ${outcome} → actual UI PDF/code/sign/wait/staff issue, single dispatch @jury`, async ({
    browser,
    sessions,
    baseURL,
  }, info) => {
    const client = await actor(browser, sessions, "client", baseURL!);
    const staff = await actor(browser, sessions, "specialist", baseURL!);
    let releaseSign = () => {};
    let releaseIssue = () => {};
    try {
      const errors: string[] = [];
      for (const page of [client.page, staff.page])
        page.on("console", (message) => {
          if (message.type() === "error") errors.push(message.text());
        });
      if (outcome === "counteroffer")
        await client.page.emulateMedia({ reducedMotion: "reduce" });
      let app = await decide(
        client.context,
        staff.context,
        outcome === "counteroffer"
          ? {
              revenue: "500000.00",
              expenses: "400000.00",
              debt: "20000.00",
            }
          : {},
      );
      const revision = app.revisions.find(
        (value) => value.id === app.current_revision_id,
      )!;
      expect(revision.assessment!.decision!.outcome).toBe(outcome);
      const offered = currentOffer(app)!;
      expect(offered.comparison.source_revision_id).toBe(revision.id);
      await showApp(client.page, app);
      if (outcome === "counteroffer")
        await expect(
          client.page.getByRole("region", {
            name: "Сравнение условий",
            exact: true,
          }),
        ).toBeVisible();
      await uiAction(client.page, "Принять предложение");
      app = await getApp(client.context, app.id);
      expect(app.status).toBe("accepted");
      await client.page
        .getByRole("button", { name: "Подписать договор", exact: true })
        .click();
      const review = client.page.getByRole("dialog", {
        name: "Просмотр договора",
        exact: true,
      });
      const confirmReview = review.getByRole("button", {
        name: "Подписать договор",
        exact: true,
      });
      await expect(confirmReview).toBeDisabled();
      const downloaded = client.page.waitForEvent("download");
      await review
        .getByRole("link", {
          name: "Скачать исходный договор (PDF)",
          exact: true,
        })
        .click();
      const download = await downloaded;
      const destination = info.outputPath(`${outcome}-original.pdf`);
      await download.saveAs(destination);
      const bytes = readFileSync(destination);
      expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
      const agreement = currentOffer(app)!.agreement!;
      const stored = await client.context.request.get(
        `/api/v1/agreements/${agreement.id}/`,
      );
      const document = (await stored.json()).documents.find(
        (value: { kind: string }) => value.kind === "original",
      );
      expect(createHash("sha256").update(bytes).digest("hex")).toBe(
        document.pdf_sha256,
      );
      expect(document.pdf_sha256).not.toBe(agreement.document_hash);

      let signs = 0;
      let signStarted!: () => void;
      const sending = new Promise<void>((resolve) => {
        signStarted = resolve;
      });
      const signGate = new Promise<void>((resolve) => {
        releaseSign = resolve;
      });
      await client.page.route("**/sign/", async (route) => {
        signs++;
        signStarted();
        await signGate;
        await route.continue();
      });
      await review.getByRole("checkbox").focus();
      await client.page.keyboard.press("Space");
      await confirmReview.click();
      const code = client.page.getByRole("dialog", {
        name: "Подтверждение подписания",
        exact: true,
      });
      await expect(code).toContainText("Сообщение не отправляется");
      await sending;
      await expect(code.getByLabel("Шестизначный демо-код")).toHaveValue(
        /^\d{6}$/,
      );
      expect(signs).toBe(1);
      expect((await getApp(client.context, app.id)).status).toBe("accepted");
      await client.page.keyboard.press("Escape");
      await expect(code).toBeVisible();
      releaseSign();
      const signedNotice = client.page.getByRole("dialog", {
        name: "Договор подписан в демо-режиме",
        exact: true,
      });
      await expect(signedNotice).toBeVisible();
      await signedNotice
        .getByRole("button", { name: "Закрыть", exact: true })
        .click();
      app = await getApp(client.context, app.id);
      expect(app.status).toBe("signed");
      expect(currentOffer(app)!.agreement!.disbursement).toBeNull();
      await expect(
        client.page.getByText(
          "Условная подпись сохранена. Ожидается моделируемая выдача специалистом.",
          { exact: true },
        ),
      ).toBeVisible();
      await expect
        .poll(async () =>
          currentOffer(
            await getApp(client.context, app.id),
          )!.agreement!.documents.some((value) => value.kind === "signed_copy"),
        )
        .toBe(true);
      await client.page
        .getByRole("button", { name: "Обновить карточку", exact: true })
        .click();
      await expect(
        client.page.getByRole("link", {
          name: "Скачать копию с демо-отметкой (PDF)",
          exact: true,
        }),
      ).toBeVisible();

      await showApp(staff.page, app, true);
      await staff.page
        .getByRole("button", { name: "Моделировать выдачу", exact: true })
        .click();
      const issue = staff.page.getByRole("dialog", {
        name: "Моделировать выдачу",
        exact: true,
      });
      let issues = 0;
      let issueStarted!: () => void;
      const issuing = new Promise<void>((resolve) => {
        issueStarted = resolve;
      });
      const issueGate = new Promise<void>((resolve) => {
        releaseIssue = resolve;
      });
      await staff.page.route("**/disburse/", async (route) => {
        issues++;
        issueStarted();
        await issueGate;
        await route.continue();
      });
      await issue
        .getByRole("button", { name: "Подтвердить", exact: true })
        .evaluate((element) => {
          (element as HTMLButtonElement).click();
          (element as HTMLButtonElement).click();
        });
      await issuing;
      await expect(
        issue.getByRole("button", { name: "Подтвердить", exact: true }),
      ).toBeDisabled();
      expect(issues).toBe(1);
      expect((await getApp(client.context, app.id)).status).toBe("signed");
      releaseIssue();
      await expect
        .poll(async () => (await getApp(client.context, app.id)).status)
        .toBe("issued");
      await expect(
        staff.page.getByText(
          "Назначение специалиста в текущем состоянии недоступно.",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(
        staff.page.getByText(
          "Свободную заявку может взять в работу специалист.",
          { exact: true },
        ),
      ).toHaveCount(0);
      await client.page
        .getByRole("button", { name: "Обновить карточку", exact: true })
        .click();
      const issued = client.page.getByRole("dialog", {
        name: "Демо-выдача завершена",
        exact: true,
      });
      await expect(issued).toBeVisible();
      await expect(issued).toContainText("Реального перевода денег не было");
      if (outcome === "counteroffer")
        await expect(issued.getByText("✓", { exact: true })).toHaveCSS(
          "animation-name",
          "none",
        );
      await issued
        .getByRole("button", { name: "Закрыть", exact: true })
        .click();
      await expect(issued).toHaveCount(0);
      const final = await getApp(client.context, app.id);
      expect(currentOffer(final)!.agreement!.disbursement!.amount).toBe(
        offered.amount,
      );
      const events = await client.context.request.get(
        `/api/v1/applications/${app.id}/events/`,
      );
      const history = (await events.json()).results as { event_type: string }[];
      expect(
        history.filter((event) => event.event_type === "signed"),
      ).toHaveLength(1);
      expect(
        history.filter((event) => event.event_type === "issued"),
      ).toHaveLength(1);
      const original = await client.context.request.get(
        `/api/v1/agreements/${agreement.id}/pdf/`,
      );
      expect(await original.body()).toEqual(bytes);
      await client.page.reload();
      await expect(client.page.getByRole("dialog")).toHaveCount(0);
      await expect(
        client.page.getByText("Выдача смоделирована", { exact: true }),
      ).toBeVisible();
      await expect(
        client.page.getByRole("button", { name: "Савелий", exact: true }),
      ).toHaveCount(0);
      expect(signs).toBe(1);
      expect(issues).toBe(1);
      expect(errors).toEqual([]);
    } finally {
      releaseSign();
      releaseIssue();
      await client.context.close();
      await staff.context.close();
    }
  });
}

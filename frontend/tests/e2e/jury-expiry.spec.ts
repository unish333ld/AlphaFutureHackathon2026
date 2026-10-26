import { execFileSync } from "node:child_process";
import { test, expect, actor, decide, getApp, post, showApp } from "./fixtures";
import { currentOffer } from "../../src/entities/credit";

test.use({ trace: "off" });

// There is deliberately no privileged HTTP "test clock" endpoint in the app.
// Explicit opt-in permits fixture maintenance only in a dedicated QA project.
const project = process.env.E2E_ISOLATED_COMPOSE_PROJECT;
for (const phase of ["offer", "signature"] as const) {
  test(`jury: actual ${phase} deadline expiry is authoritative in UI @jury-expiry`, async ({
    browser,
    sessions,
    baseURL,
    browserName,
  }) => {
    test.skip(
      browserName !== "chromium" || !project?.startsWith("alfa-jury-qa-"),
      "Requires explicitly named isolated QA Compose project and host Docker CLI",
    );
    if (!project || !/^alfa-jury-qa-[a-z0-9-]+$/.test(project))
      throw new Error("Unsafe QA project name");
    const origin = new URL(baseURL!);
    const bound = execFileSync(
      "docker",
      ["compose", "-p", project, "port", "frontend", "80"],
      { cwd: "..", encoding: "utf8", timeout: 10000 },
    ).trim();
    if (
      !["127.0.0.1", "localhost"].includes(origin.hostname) ||
      !origin.port ||
      !bound.endsWith(`:${origin.port}`)
    )
      throw new Error(
        "Frontend origin does not belong to the isolated QA project",
      );
    const client = await actor(browser, sessions, "client", baseURL!);
    const staff = await actor(browser, sessions, "specialist", baseURL!);
    try {
      let app = await decide(client.context, staff.context);
      const offer = currentOffer(app)!;
      if (phase === "signature")
        app = await post(client.context, `offers/${offer.id}/accept/`, {
          lock_version: app.lock_version,
        });
      await showApp(client.page, app);
      let signs = 0;
      client.page.on("request", (request) => {
        if (request.method() === "POST" && request.url().endsWith("/sign/"))
          signs++;
      });
      if (phase === "signature") {
        await client.page.clock.install();
        await client.page.clock.pauseAt(new Date(Date.now() + 100));
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
        await expect(
          client.page.getByRole("dialog", {
            name: "Подтверждение подписания",
            exact: true,
          }),
        ).toBeVisible();
      }
      if (!/^[0-9a-f-]{36}$/i.test(offer.id))
        throw new Error("Invalid fixture ID");
      execFileSync(
        "docker",
        [
          "compose",
          "-p",
          project,
          "exec",
          "-T",
          "web",
          "python",
          "manage.py",
          "shell",
          "-c",
          `from django.conf import settings; from django.utils import timezone; from datetime import timedelta; from offers.models import Offer; assert settings.DEMO_MODE; assert Offer.objects.filter(pk='${offer.id}').update(${phase === "offer" ? "expires_at" : "sign_before"}=timezone.now()-timedelta(seconds=1)) == 1`,
        ],
        { cwd: "..", stdio: "pipe", timeout: 10000 },
      );
      if (phase === "signature") {
        await client.page.clock.runFor(1001);
        const dialog = client.page.getByRole("dialog", {
          name: "Подтверждение подписания",
          exact: true,
        });
        await expect(dialog.getByRole("alert")).toBeVisible();
        await dialog
          .getByRole("button", { name: "Закрыть", exact: true })
          .click();
        await client.page.clock.resume();
        expect(signs).toBe(1);
      } else {
        await client.page
          .getByRole("button", { name: "Принять предложение", exact: true })
          .click();
        await expect(client.page.getByRole("alert").first()).toBeVisible();
      }
      const expired = await getApp(client.context, app.id);
      expect(expired.status).toBe("expired");
      expect(currentOffer(expired)!.agreement?.signed_at ?? null).toBeNull();
      await client.page.reload();
      await expect(
        client.page.getByRole("heading", {
          name: `Заявка ${app.number}`,
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        client.page.getByRole("button", {
          name: "Подписать договор",
          exact: true,
        }),
      ).toHaveCount(0);
      await expect(
        client.page.getByRole("button", {
          name: "Принять предложение",
          exact: true,
        }),
      ).toHaveCount(0);
      expect(signs).toBe(phase === "signature" ? 1 : 0);
      await showApp(staff.page, expired, true);
      await expect(
        staff.page.getByText(
          "Назначение специалиста в текущем состоянии недоступно.",
          { exact: true },
        ),
      ).toBeVisible();
    } finally {
      await client.context.close();
      await staff.context.close();
    }
  });
}

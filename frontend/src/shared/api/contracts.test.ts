import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cents,
  currentAssessment,
  currentOffer,
  currentRevision,
  money,
  normalizeMoney,
} from "../../entities/credit";
import { ApiError, normalizeError } from "./errors";
import { api, type Application, type Revision } from "./client";
import { beginIntent, clearIntent, clearIntents, readIntent } from "./intent";
import { request, setCsrf } from "./http";

describe("exact decimal money", () => {
  it.each([
    ["1 000 000,01", "1000000.01"],
    ["00012", "12.00"],
    ["0", "0.00"],
    ["9999999999999999.99", "9999999999999999.99"],
  ])("normalizes %s without floating point", (value, expected) => {
    expect(normalizeMoney(value)).toBe(expected);
    expect(cents(value)).toBe(BigInt(expected.replace(".", "")));
  });
  it.each(["", "1.001", "-1", "Infinity", "1e6", "<script>", "1,2,3"])(
    "rejects %s",
    (value) => expect(normalizeMoney(value)).toBeNull(),
  );
  it("does not invent missing money or lose precision", () => {
    expect(money(null)).toBe("Нет данных");
    expect(money("9999999999999999.99").replace(/\s/g, "")).toBe(
      "9999999999999999,99₽",
    );
  });
});
describe("revision identity", () => {
  it("does not display an assessment from an older check attempt", () => {
    const revision = {
      id: "current",
      checks: [{ attempt: 2 }],
      assessment: { revision: "current", checks_attempt: 1 },
    } as Revision;
    expect(currentAssessment(revision)).toBeNull();
    expect(
      currentAssessment({
        ...revision,
        assessment: { ...revision.assessment!, checks_attempt: 2 },
      }),
    ).toBeTruthy();
  });
  it("uses the pointer rather than array ordering", () => {
    const app = {
      current_revision_id: "b",
      revisions: [{ id: "b" }, { id: "a" }],
    } as Application;
    expect(currentRevision(app)?.id).toBe("b");
    expect(
      currentRevision({ ...app, current_revision_id: "missing" }),
    ).toBeNull();
  });
  it("rejects another revision assessment and decision", () => {
    const rev = {
      id: "a",
      assessment: {
        id: "assessment",
        revision: "b",
        decision: { assessment: "other", offer: { id: "offer" } },
      },
    } as Revision;
    expect(currentAssessment(rev)).toBeNull();
    expect(
      currentOffer({
        current_revision_id: "a",
        revisions: [
          { ...rev, assessment: { ...rev.assessment!, revision: "a" } },
        ],
      } as Application),
    ).toBeNull();
  });
});
describe("DRF errors", () => {
  it("supports fields, detail, non_field_errors and arrays", () => {
    expect(
      normalizeError(
        { amount: ["Too high"], non_field_errors: ["Conflict"] },
        400,
      ),
    ).toMatchObject({ message: "Conflict", fields: { amount: "Too high" } });
    expect(normalizeError(["One", ["Two"]], 400).message).toBe("One Two");
    expect(
      normalizeError({ detail: "Forbidden", code: "permission_denied" }, 403),
    ).toMatchObject({ message: "Forbidden", code: "permission_denied" });
  });
  it.each([403, 404, 409, 429, 503, 0])("has a safe message for %i", (status) =>
    expect(
      normalizeError("<html>secret traceback</html>", status).message,
    ).not.toContain("secret"),
  );
  it("never exposes dependency details", () => {
    expect(
      normalizeError({ detail: "SQL password" }, 503).message,
    ).not.toContain("password");
    expect(new ApiError(503, null).uncertain).toBe(true);
    expect(new ApiError(409, null).uncertain).toBe(false);
  });
});
describe("issuance intent survives an uncertain response", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "sessionStorage",
      new (class {
        [key: string]: unknown;
        getItem(k: string) {
          return typeof this[k] === "string" ? this[k] : null;
        }
        setItem(k: string, v: string) {
          this[k] = v;
        }
        removeItem(k: string) {
          delete this[k];
        }
      })(),
    );
  });
  afterEach(() => vi.unstubAllGlobals());
  it("reuses a stable user/agreement UUID and stores no credit payload", () => {
    const intent = beginIntent("user", "agreement");
    expect(beginIntent("user", "agreement").key).toBe(intent.key);
    expect(readIntent("other", "agreement")).toBeNull();
    expect(Object.keys(intent).sort()).toEqual([
      "agreementId",
      "createdAt",
      "key",
      "pending",
    ]);
    clearIntent("user", "agreement");
    expect(readIntent("user", "agreement")).toBeNull();
  });
  it("clears only issuance keys on logout", () => {
    sessionStorage.setItem("unrelated", "keep");
    beginIntent("user", "agreement");
    clearIntents();
    expect(readIntent("user", "agreement")).toBeNull();
    expect(sessionStorage.getItem("unrelated")).toBe("keep");
  });
  it("refuses dispatch if stable storage is unavailable", () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => null,
      setItem: () => {
        throw new Error("denied");
      },
    });
    expect(() => beginIntent("u", "a")).toThrow("denied");
  });
});
describe("session API transport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setCsrf(null);
  });
  it("does not dispatch a request cancelled before it starts", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);
    const controller = new AbortController();
    controller.abort();
    await expect(request("me/", { signal: controller.signal })).rejects.toBe(
      controller.signal.reason,
    );
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("does not send queued application reads after their page was cancelled", async () => {
    const release: (() => void)[] = [];
    const fetcher = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.signal?.aborted) return Promise.reject(init.signal.reason);
      return new Promise<Response>((resolve) => {
        release.push(() => resolve(new Response("{}")));
      });
    });
    vi.stubGlobal("fetch", fetcher);
    const controller = new AbortController();
    const active = Array.from({ length: 4 }, (_, index) =>
      api.application(`active-${index}`),
    );
    const queued = api.application("queued", false, controller.signal);
    expect(fetcher).toHaveBeenCalledTimes(4);
    controller.abort();
    release.forEach((resolve) => resolve());
    const results = await Promise.allSettled([...active, queued]);
    expect(results[4]).toMatchObject({
      status: "rejected",
      reason: controller.signal.reason,
    });
    expect(fetcher).toHaveBeenCalledTimes(4);
  });
  it("uses cookies and rotated CSRF, not JWT", async () => {
    setCsrf("rotated");
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "one" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    await request("applications/", {
      method: "POST",
      body: { amount: "100000.01" },
    });
    const [path, init] = fetcher.mock.calls[0]!;
    expect(path).toBe("/api/v1/applications/");
    expect(init.credentials).toBe("include");
    expect(init.headers.get("X-CSRFToken")).toBe("rotated");
    expect(init.headers.has("Authorization")).toBe(false);
    expect(JSON.parse(init.body).amount).toBe("100000.01");
  });
  it("does not retry a mutation after a lost response", async () => {
    setCsrf("csrf");
    const fetcher = vi.fn().mockRejectedValue(new TypeError("network"));
    vi.stubGlobal("fetch", fetcher);
    await expect(
      request("applications/", { method: "POST", body: {} }),
    ).rejects.toMatchObject({ status: 0 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects absolute URLs and disallowed actions before dispatch", async () => {
    await expect(request("https://example.com/")).rejects.toThrow();
    expect(() =>
      api.action(
        {
          action: "decide",
          allowed: false,
          target_id: null,
          reason_code: "role_required",
        },
        0,
      ),
    ).toThrow();
  });
});

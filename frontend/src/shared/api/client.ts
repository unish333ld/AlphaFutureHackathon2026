import type { components, operations } from "./schema";
import { request } from "./http";

export type Schema = components["schemas"];
export type Application = Schema["Application"];
export type Revision = Schema["Revision"];
export type Product = Schema["Product"];
export type Company = Schema["Company"];
export type User = Schema["User"];
export type Action = Schema["AvailableAction"];
export type ActionName = Schema["ActionEnum"];
export type Status = Schema["ApplicationStatusEnum"];
export type Agreement = Schema["Agreement"];
export type AssistantConversation = Schema["Conversation"];
export type AssistantMessage = Schema["Message"];
export type AssistantReply = Schema["AssistantReply"];
export type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
export type QueueFilters = NonNullable<
  operations["v1_staff_applications_list"]["parameters"]["query"]
>;

let activeDetails = 0;
const detailQueue: (() => void)[] = [];
async function limitedDetail<T>(fn: () => Promise<T>): Promise<T> {
  if (activeDetails >= 4)
    await new Promise<void>((resolve) => detailQueue.push(resolve));
  else activeDetails++;
  try {
    return await fn();
  } finally {
    const next = detailQueue.shift();
    if (next) next();
    else activeDetails--;
  }
}
const query = (params: Record<string, string | number | undefined>) => {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined && value !== "") result.set(key, String(value));
  return result.toString() ? `?${result}` : "";
};
async function catalog<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const rows: T[] = [];
  let page = 1;
  for (;;) {
    const result = await request<Page<T>>(`${path}${query({ page })}`, {
      signal,
    });
    rows.push(...result.results);
    if (!result.next) return rows;
    page++;
  }
}
export const actionPaths: Record<ActionName, (id: string) => string> = {
  update_draft: (id) => `applications/${id}/`,
  submit: (id) => `applications/${id}/submit/`,
  retry_checks: (id) => `applications/${id}/retry-checks/`,
  provide_information: (id) => `applications/${id}/provide-information/`,
  revise: (id) => `applications/${id}/revise/`,
  claim: (id) => `staff/applications/${id}/claim/`,
  release: (id) => `staff/applications/${id}/release/`,
  request_information: (id) => `staff/applications/${id}/request-information/`,
  decide: (id) => `staff/applications/${id}/decide/`,
  accept_offer: (id) => `offers/${id}/accept/`,
  decline_offer: (id) => `offers/${id}/decline/`,
  sign_agreement: (id) => `agreements/${id}/sign/`,
  disburse: (id) => `agreements/${id}/disburse/`,
};
export const api = {
  me: (signal?: AbortSignal) => request<User>("me/", { signal }),
  login: (data: Schema["LoginRequestRequest"]) =>
    request<Schema["LoginResponse"]>("session/login/", {
      method: "POST",
      body: data,
    }),
  logout: () => request<void>("session/logout/", { method: "POST" }),
  companies: (signal?: AbortSignal) => catalog<Company>("companies/", signal),
  products: (signal?: AbortSignal) => catalog<Product>("products/", signal),
  company: (id: string, signal?: AbortSignal) =>
    request<Company>(`companies/${id}/`, { signal }),
  applications: (page = 1, status?: Status, signal?: AbortSignal) =>
    request<Page<Schema["ApplicationList"]>>(
      `applications/${query({ page, status })}`,
      { signal },
    ),
  application: (id: string, staff = false, signal?: AbortSignal) =>
    limitedDetail(() =>
      request<Application>(`${staff ? "staff/" : ""}applications/${id}/`, {
        signal,
      }),
    ),
  queue: (params: QueueFilters, signal?: AbortSignal) =>
    request<Page<Schema["StaffApplicationList"]>>(
      `staff/applications/${query(params)}`,
      { signal },
    ),
  create: (data: Schema["ApplicationCreateRequest"]) =>
    request<Application>("applications/", { method: "POST", body: data }),
  patch: (id: string, data: Schema["PatchedDraftUpdateRequest"]) =>
    request<Application>(`applications/${id}/`, {
      method: "PATCH",
      body: data,
    }),
  revise: (action: Action, data: Schema["RevisionSubmitRequest"]) => {
    if (
      !action.allowed ||
      !action.target_id ||
      !["provide_information", "revise"].includes(action.action)
    )
      throw new Error("Действие недоступно. Обновите карточку.");
    return request<Application>(actionPaths[action.action](action.target_id), {
      method: "POST",
      body: data,
    });
  },
  action: (
    action: Action,
    version: number,
    extra: {
      question?: string;
      document_hash?: string;
      confirm_simulation?: boolean;
    } = {},
    idempotencyKey?: string,
  ) => {
    if (
      !action.allowed ||
      !action.target_id ||
      !/^[0-9a-f-]{36}$/i.test(action.target_id)
    )
      throw new Error("Действие недоступно. Обновите карточку.");
    return request<Application | Agreement | Schema["Disbursement"]>(
      actionPaths[action.action](action.target_id),
      {
        method: action.action === "update_draft" ? "PATCH" : "POST",
        body: { lock_version: version, ...extra },
        idempotencyKey,
      },
    );
  },
  agreement: (id: string) => request<Agreement>(`agreements/${id}/`),
  events: (id: string, page: number, signal?: AbortSignal) =>
    request<Page<Schema["Event"]>>(
      `applications/${id}/events/${query({ page })}`,
      { signal },
    ),
  calculator: (data: Schema["PaymentRequestRequest"]) =>
    request<Schema["PaymentResponse"]>("calculator/payment/", {
      method: "POST",
      body: data,
    }),
  assistantConversations: (page = 1, signal?: AbortSignal) =>
    request<Page<AssistantConversation>>(
      `assistant/conversations/${query({ page })}`,
      { signal },
    ),
  assistantConversation: (id: string, signal?: AbortSignal) =>
    request<AssistantConversation>(`assistant/conversations/${id}/`, {
      signal,
    }),
  assistantCreateConversation: (company_id: string, application_id?: string) =>
    request<AssistantConversation>("assistant/conversations/", {
      method: "POST",
      body: { company_id, ...(application_id ? { application_id } : {}) },
    }),
  assistantMessages: (id: string, page = 1, signal?: AbortSignal) =>
    request<Page<AssistantMessage>>(
      `assistant/conversations/${id}/messages/${query({ page })}`,
      { signal },
    ),
  assistantSend: (id: string, text: string, expected_version: number) =>
    request<AssistantReply>(`assistant/conversations/${id}/messages/`, {
      method: "POST",
      body: { text, expected_version },
      timeoutMs: 90_000,
    }),
};

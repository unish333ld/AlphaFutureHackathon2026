const prefix = "credit:issue:v1:";
export type IssueIntent = {
  key: string;
  agreementId: string;
  createdAt: string;
  pending: true;
};
const storageKey = (user: string, agreement: string) =>
  `${prefix}${user}:${agreement}`;
export function readIntent(
  user: string,
  agreement: string,
): IssueIntent | null {
  try {
    const value: unknown = JSON.parse(
      sessionStorage.getItem(storageKey(user, agreement)) ?? "null",
    );
    if (!value || typeof value !== "object") return null;
    const item = value as Partial<IssueIntent>;
    return typeof item.key === "string" &&
      /^[0-9a-f-]{36}$/i.test(item.key) &&
      item.agreementId === agreement &&
      typeof item.createdAt === "string" &&
      item.pending === true
      ? (item as IssueIntent)
      : null;
  } catch {
    return null;
  }
}
export function beginIntent(user: string, agreement: string): IssueIntent {
  const existing = readIntent(user, agreement);
  if (existing) return existing;
  const value: IssueIntent = {
    key: crypto.randomUUID(),
    agreementId: agreement,
    createdAt: new Date().toISOString(),
    pending: true,
  };
  // Refuse to dispatch if intent cannot survive a reload in this tab.
  sessionStorage.setItem(storageKey(user, agreement), JSON.stringify(value));
  return value;
}
export function clearIntent(user: string, agreement: string) {
  try {
    sessionStorage.removeItem(storageKey(user, agreement));
  } catch {
    /* No credentials or payload are stored. */
  }
}
export function clearIntents() {
  try {
    for (const key of Object.keys(sessionStorage))
      if (key.startsWith(prefix)) sessionStorage.removeItem(key);
  } catch {
    /* storage can be disabled */
  }
}

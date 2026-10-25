export type AssistantDraft = {
  company: string;
  product: string;
  amount: string;
  term_months: number;
  purpose: string;
  requires_user_confirmation: true;
};

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseAssistantDraft(
  value: unknown,
  expectedCompany?: string,
): AssistantDraft | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (
    item.requires_user_confirmation !== true ||
    typeof item.company !== "string" ||
    !uuid.test(item.company) ||
    (expectedCompany && item.company !== expectedCompany) ||
    typeof item.product !== "string" ||
    !uuid.test(item.product) ||
    typeof item.amount !== "string" ||
    !/^\d{1,16}\.\d{2}$/.test(item.amount) ||
    typeof item.term_months !== "number" ||
    !Number.isInteger(item.term_months) ||
    item.term_months < 1 ||
    item.term_months > 120 ||
    typeof item.purpose !== "string" ||
    !item.purpose.trim() ||
    item.purpose.length > 500
  )
    return null;
  return item as AssistantDraft;
}

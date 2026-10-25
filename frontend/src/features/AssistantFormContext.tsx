import {
  createContext,
  useContext,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
  type ReactNode,
  type MutableRefObject,
} from "react";
import type { AssistantDraft } from "./assistantDraft";

export type FormSnapshot = {
  company: string;
  product: string;
  amount: string;
  term_months: string;
  purpose: string;
  fingerprint: string;
};
export type AssistantForm = {
  snapshot: () => FormSnapshot;
  apply: (draft: AssistantDraft, expected: string) => boolean;
};
type Bridge = {
  form: MutableRefObject<AssistantForm | null>;
  transfer: MutableRefObject<AssistantDraft | null>;
  selection: { company: string; product: string } | null;
  setSelection: Dispatch<SetStateAction<Bridge["selection"]>>;
};
const Context = createContext<Bridge | null>(null);
export function AssistantFormProvider({ children }: { children: ReactNode }) {
  const form = useRef<AssistantForm | null>(null);
  const transfer = useRef<AssistantDraft | null>(null);
  const [selection, setSelection] = useState<Bridge["selection"]>(null);
  const bridge = useMemo(
    () => ({ form, transfer, selection, setSelection }),
    [selection],
  );
  return <Context.Provider value={bridge}>{children}</Context.Provider>;
}
export function useAssistantForm() {
  const bridge = useContext(Context);
  if (!bridge) throw new Error("Assistant form provider is missing");
  return bridge;
}

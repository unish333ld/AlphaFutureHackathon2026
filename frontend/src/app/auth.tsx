import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type User } from "../shared/api/client";
import { ApiError } from "../shared/api/errors";
import { csrfToken, setCsrf } from "../shared/api/http";
import { clearIntents } from "../shared/api/intent";

type Auth = {
  user: User | null;
  loading: boolean;
  startupError: unknown;
  expired: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  check: () => Promise<void>;
};
const AuthContext = createContext<Auth | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const current = useRef<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [startupError, setStartupError] = useState<unknown>(null);
  const [expired, setExpired] = useState(false);
  const channel = useRef<BroadcastChannel | null>(null);
  const checking = useRef(false);
  const authEpoch = useRef(0);
  const authTransition = useRef(false);
  async function applyUser(
    next: User | null,
    preserveSame = true,
    epoch = authEpoch.current,
  ) {
    if (epoch !== authEpoch.current) return;
    if (
      !preserveSame ||
      current.current?.id !== next?.id ||
      current.current?.system_role !== next?.system_role
    ) {
      await queryClient.cancelQueries();
      if (epoch !== authEpoch.current) return;
      queryClient.clear();
      // Initial /me on a reload must retain this user's pending issuance key.
      // The key is user-scoped; a known account change or logout clears it.
      if (current.current || !next || !preserveSame) clearIntents();
    }
    current.current = next;
    setUser(next);
    setExpired(false);
    setStartupError(null);
  }
  async function check() {
    if (checking.current || authTransition.current) return;
    checking.current = true;
    const epoch = authEpoch.current;
    try {
      const next = await api.me();
      if (epoch === authEpoch.current) await applyUser(next, true, epoch);
    } catch (error) {
      if (epoch !== authEpoch.current) return;
      if (error instanceof ApiError && error.status === 403) {
        if (current.current) setExpired(true);
        else setUser(null);
      } else if (!current.current) setStartupError(error);
    } finally {
      checking.current = false;
      if (epoch === authEpoch.current) setLoading(false);
      else if (!current.current) void check();
    }
  }
  useEffect(() => {
    void check();
    const verify = () => {
      if (document.visibilityState === "visible") void check();
    };
    const listen = () => {
      void check();
    };
    window.addEventListener("credit:check-session", listen);
    window.addEventListener("focus", verify);
    if ("BroadcastChannel" in window) {
      channel.current = new BroadcastChannel("credit-session");
      channel.current.onmessage = () => {
        const epoch = ++authEpoch.current;
        authTransition.current = false;
        setCsrf(null);
        void queryClient.cancelQueries().then(() => {
          if (epoch !== authEpoch.current) return;
          queryClient.clear();
          clearIntents();
          current.current = null;
          setUser(null);
          setLoading(true);
          void check();
        });
      };
    }
    return () => {
      window.removeEventListener("credit:check-session", listen);
      window.removeEventListener("focus", verify);
      channel.current?.close();
    };
    // One listener per provider; current user is held in a ref for async session checks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function login(username: string, password: string) {
    const epoch = ++authEpoch.current;
    authTransition.current = true;
    try {
      await csrfToken(true);
      const response = await api.login({ username, password });
      if (epoch !== authEpoch.current)
        throw new Error("Session changed during login");
      setCsrf(response.csrf_token);
      await applyUser(response.user, true, epoch);
      setLoading(false);
      await queryClient.invalidateQueries();
      channel.current?.postMessage("login");
      return response.user;
    } finally {
      if (epoch === authEpoch.current) authTransition.current = false;
    }
  }
  async function logout() {
    const epoch = ++authEpoch.current;
    authTransition.current = true;
    try {
      await api.logout();
      if (epoch !== authEpoch.current) return;
      await applyUser(null, false, epoch);
      setCsrf(null);
      channel.current?.postMessage("logout");
    } finally {
      if (epoch === authEpoch.current) authTransition.current = false;
    }
  }
  return (
    <AuthContext.Provider
      value={{ user, loading, startupError, expired, login, logout, check }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("AuthProvider missing");
  return auth;
}

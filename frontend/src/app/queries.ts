import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./auth";
import { api } from "../shared/api/client";

export function useScope(company = "all") {
  const { user } = useAuth();
  if (!user) throw new Error("Session required");
  return ["user", user.id, user.system_role, company] as const;
}
export function useCatalogs() {
  const scope = useScope();
  const companies = useQuery({
    queryKey: [...scope, "companies"],
    queryFn: ({ signal }) => api.companies(signal),
    staleTime: 60000,
  });
  const products = useQuery({
    queryKey: [...scope, "products"],
    queryFn: ({ signal }) => api.products(signal),
    staleTime: 60000,
  });
  return { companies, products };
}
export function useApplication(id: string) {
  const { user } = useAuth();
  const scope = useScope();
  return useQuery({
    queryKey: [...scope, "application", id],
    queryFn: ({ signal }) =>
      api.application(id, user?.system_role === "specialist", signal),
    refetchInterval: (query) =>
      query.state.data?.status === "signed" ? 5000 : false,
  });
}
export function useRefreshCredit() {
  const { user } = useAuth();
  const client = useQueryClient();
  return async () => {
    if (!user) return;
    await client.invalidateQueries({
      queryKey: ["user", user.id],
      predicate: (query) =>
        ["application", "applications", "queue", "events"].some((key) =>
          query.queryKey.includes(key),
        ),
    });
  };
}

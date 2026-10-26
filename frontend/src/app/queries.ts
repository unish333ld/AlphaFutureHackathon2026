import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./auth";
import {
  api,
  type Application,
  type Page,
  type Schema,
} from "../shared/api/client";

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
      [
        "submitted",
        "checking",
        "review",
        "needs_info",
        "offered",
        "accepted",
        "signed",
      ].includes(query.state.data?.status ?? "")
        ? 5000
        : false,
  });
}
export function useRefreshCredit() {
  const { user } = useAuth();
  const client = useQueryClient();
  return async (updated?: Application) => {
    if (!user) return;
    if (updated) {
      client.setQueriesData<Page<Schema["ApplicationList"]>>(
        {
          queryKey: ["user", user.id],
          predicate: (query) => query.queryKey.includes("applications"),
        },
        (page) =>
          page
            ? {
                ...page,
                results: page.results.map((row) =>
                  row.id === updated.id
                    ? {
                        ...row,
                        status: updated.status,
                        lock_version: updated.lock_version,
                        updated_at: updated.updated_at,
                      }
                    : row,
                ),
              }
            : page,
      );
    }
    await client.invalidateQueries({
      queryKey: ["user", user.id],
      predicate: (query) =>
        ["application", "applications", "queue", "events"].some((key) =>
          query.queryKey.includes(key),
        ),
    });
  };
}

import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  RouterProvider,
  useRouteError,
} from "react-router-dom";
import { AuthProvider, useAuth } from "./app/auth";
import Shell from "./app/Shell";
import { Empty, Loading, Panel } from "./shared/ui/kit";
import { LinkButton } from "./shared/ui/navigation";
import { ApiError } from "./shared/api/errors";
import "./shared/styles/global.css";

const Login = lazy(() => import("./pages/LoginPage"));
const Home = lazy(() => import("./pages/HomePage"));
const Loans = lazy(() => import("./pages/LoansPage"));
const Queue = lazy(() => import("./pages/QueuePage"));
const Application = lazy(() => import("./pages/ApplicationPage"));
const Edit = lazy(() => import("./features/ApplicationForm"));
const Create = lazy(() =>
  import("./features/ApplicationForm").then((module) => ({
    default: module.NewApplicationPage,
  })),
);
const Submitted = lazy(() => import("./pages/SubmittedPage"));
function Role({ role }: { role: "client" | "specialist" }) {
  const { user } = useAuth();
  return user?.system_role === role ? (
    <Outlet />
  ) : (
    <Navigate
      to={user?.system_role === "specialist" ? "/staff" : "/app"}
      replace
    />
  );
}
function Boundary() {
  const error = useRouteError();
  return (
    <main style={{ maxWidth: 700, margin: "64px auto", padding: 20 }}>
      <Panel>
        <Empty title="Не удалось открыть экран">
          Данные на сервере не изменены. Попробуйте открыть кабинет заново.
        </Empty>
        <a href="/">Открыть кабинет</a>
      </Panel>
      {import.meta.env.DEV ? <pre>{String(error)}</pre> : null}
    </main>
  );
}
const router = createBrowserRouter([
  { path: "/login", element: <Login />, errorElement: <Boundary /> },
  {
    element: <Shell />,
    errorElement: <Boundary />,
    children: [
      { path: "/", element: <Navigate to="/app" replace /> },
      {
        element: <Role role="client" />,
        children: [
          { path: "/app", element: <Home /> },
          { path: "/app/loans", element: <Loans /> },
          { path: "/app/loans/new", element: <Create /> },
          { path: "/app/loans/:id", element: <Application /> },
          { path: "/app/loans/:id/edit", element: <Edit /> },
          { path: "/app/loans/:id/submitted", element: <Submitted /> },
        ],
      },
      {
        element: <Role role="specialist" />,
        children: [
          { path: "/staff", element: <Queue /> },
          { path: "/staff/applications/:id", element: <Application /> },
        ],
      },
      {
        path: "*",
        element: (
          <Panel>
            <Empty
              title="Страница не найдена"
              action={<LinkButton to="/">В кабинет</LinkButton>}
            >
              Проверьте адрес страницы.
            </Empty>
          </Panel>
        ),
      },
    ],
  },
]);
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 20_000,
      gcTime: 300_000,
      retry: (attempt, error) =>
        attempt < 1 && error instanceof ApiError && error.status >= 500,
      refetchOnWindowFocus: true,
    },
    mutations: { retry: false },
  },
});
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Suspense fallback={<Loading />}>
          <RouterProvider router={router} />
        </Suspense>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);

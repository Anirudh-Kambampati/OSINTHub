import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Link, Outlet, RouterProvider, createBrowserRouter, type RouteObject } from "react-router";
import { AppShell } from "./components/layout/AppShell";
import { EmptyState } from "./components/ui/primitives";
import { RequireAuth, UnauthorizedRedirect } from "./context/auth";
import { EvidenceProvider } from "./context/evidence";
import { createFeedbackMutationCache, feedbackDispatcher, FeedbackProvider } from "./context/FeedbackContext";
import { ApiError } from "./lib/api";
import { HomePage } from "./pages/HomePage";
import { InvestigationLayout } from "./pages/InvestigationLayout";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { LoginPage } from "./pages/LoginPage";
import { SettingsPage } from "./pages/SettingsPage";
import { OverviewTab } from "./pages/tabs/OverviewTab";
import { MentionsTab, ProfilesTab, TimelineTab } from "./pages/tabs/OtherTabs";
import { SourcesTab } from "./pages/tabs/SourcesTab";

export function createQueryClient() {
  return new QueryClient({
    // Every mutation failure surfaces (toast or inline), including ones a component forgot to
    // handle. Settled before the per-mutation onError.
    mutationCache: createFeedbackMutationCache((error, fallback) =>
      feedbackDispatcher.notifyError?.(error, fallback),
    ),
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: false,
        retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      },
    },
  });
}

function Root() {
  return (
    <FeedbackProvider>
      <EvidenceProvider>
        <UnauthorizedRedirect />
        <Outlet />
      </EvidenceProvider>
    </FeedbackProvider>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: "login", element: <LoginPage /> },
      {
        element: (
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <HomePage /> },
          { path: "investigations", element: <InvestigationsPage /> },
          {
            path: "investigations/:id",
            element: <InvestigationLayout />,
            children: [
              { index: true, element: <OverviewTab /> },
              { path: "profiles", element: <ProfilesTab /> },
              { path: "mentions", element: <MentionsTab /> },
              { path: "timeline", element: <TimelineTab /> },
              // React Flow + dagre are the heaviest dependencies; load them only when the graph is opened.
              { path: "graph", lazy: async () => ({ Component: (await import("./pages/tabs/GraphTab")).GraphTab }) },
              { path: "sources/:group?", element: <SourcesTab /> },
            ],
          },
          { path: "settings", element: <SettingsPage /> },
          {
            path: "*",
            element: (
              <EmptyState title="Page not found" className="mt-16" action={<Link to="/" className="text-accent hover:underline">Go to overview</Link>} />
            ),
          },
        ],
      },
    ],
  },
];

const router = createBrowserRouter(routes);
const queryClient = createQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

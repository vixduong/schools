import { QueryCache, QueryClient } from "@tanstack/react-query";
import {
  createRouter,
  ErrorComponent,
  type ErrorComponentProps,
  type RouterHistory,
} from "@tanstack/react-router";
import { SignedOut } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { routeTree } from "./routeTree.gen";

/** The router and its query cache, built together: the cache sends a member whose session ended
 * (another tab signed out, it expired) back to /login and forgets their data. */
export function makeApp(history?: RouterHistory) {
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        // Only a session that was live: the first load redirects in `_app`'s beforeLoad.
        if (!(error instanceof SignedOut) || query.state.data === undefined) return;
        const redirect = router.state.location.href;
        queryClient.clear();
        router.navigate({ to: "/login", search: { redirect } });
      },
    }),
  });
  const router = createRouter({
    routeTree,
    history,
    context: { queryClient },
    defaultErrorComponent: AppError,
  });
  return { queryClient, router };
}

function AppError({ error }: ErrorComponentProps) {
  return (
    <main className="container grid max-w-[420px] gap-4 py-16">
      <h1 className="font-serif text-4xl font-light">Có lỗi xảy ra</h1>
      <p>Không tải được trang này. Kiểm tra mạng rồi tải lại; nếu vẫn lỗi, báo quản trị trường.</p>
      <Button className="justify-self-start" onClick={() => window.location.reload()}>
        Tải lại trang
      </Button>
      {import.meta.env.DEV && <ErrorComponent error={error} />}
    </main>
  );
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof makeApp>["router"];
  }
}

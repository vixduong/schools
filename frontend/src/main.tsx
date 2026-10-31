import "@fontsource/hepta-slab/latin-300.css";
import "@fontsource/hepta-slab/latin-400.css";
import "@fontsource/hepta-slab/latin-ext-300.css";
import "@fontsource/hepta-slab/latin-ext-400.css";
import "@fontsource/hepta-slab/vietnamese-300.css";
import "@fontsource/hepta-slab/vietnamese-400.css";
import "@fontsource/be-vietnam-pro/latin-400.css";
import "@fontsource/be-vietnam-pro/latin-600.css";
import "@fontsource/be-vietnam-pro/latin-400-italic.css";
import "@fontsource/be-vietnam-pro/latin-ext-400.css";
import "@fontsource/be-vietnam-pro/latin-ext-600.css";
import "@fontsource/be-vietnam-pro/latin-ext-400-italic.css";
import "@fontsource/be-vietnam-pro/vietnamese-400.css";
import "@fontsource/be-vietnam-pro/vietnamese-600.css";
import "@fontsource/be-vietnam-pro/vietnamese-400-italic.css";
import "./styles/app.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { routeTree } from "./routeTree.gen";

const queryClient = new QueryClient();
const router = createRouter({ routeTree, context: { queryClient } });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (!root) throw new Error("#root missing from index.html");
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);

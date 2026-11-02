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

import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { makeApp } from "./router";

const { queryClient, router } = makeApp();

const root = document.getElementById("root");
if (!root) throw new Error("#root missing from index.html");
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);

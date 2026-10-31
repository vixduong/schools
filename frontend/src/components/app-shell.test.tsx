import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { AppShell } from "@/components/app-shell";

test("shell shows the wordmark and the mode toggle", async () => {
  const router = createRouter({
    routeTree: createRootRoute({ component: AppShell }),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("link", { name: "sổ trường" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /chế độ (sáng|tối)/i })).toBeInTheDocument();
});

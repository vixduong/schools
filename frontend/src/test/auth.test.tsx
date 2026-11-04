import { fireEvent, screen, waitFor } from "@testing-library/react";
import { safeRedirect } from "@/lib/messages";
import { ME, renderApp } from "./render-app";

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

test("a signed-out visit goes to the login screen, which names the School", async () => {
  const { history } = await renderApp("/gradebook", (r) =>
    r.url.endsWith("/api/auth/me/") ? { status: 403 } : undefined,
  );
  expect(await screen.findByRole("heading", { name: "THCS Mẫu" })).toBeInTheDocument();
  expect(history.location.pathname).toBe("/login");
  expect(history.location.search).toContain("redirect=%2Fgradebook");
});

test("a wrong password shows one message; the right one signs in with CSRF", async () => {
  let attempts = 0;
  const { calls, history } = await renderApp("/login?redirect=%2Fgradebook", (r) => {
    if (r.url.endsWith("/api/auth/login/")) {
      attempts += 1;
      return attempts === 1
        ? { status: 400, body: { non_field_errors: ["Invalid credentials."] } }
        : { status: 200, body: ME };
    }
    if (r.url.endsWith("/api/auth/me/")) return { status: 200, body: ME };
  });
  await screen.findByRole("heading", { name: "THCS Mẫu" });
  fill("Số điện thoại hoặc email", "0912000111");
  fill("Mật khẩu", "sai");
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Sai số điện thoại, email hoặc mật khẩu.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  expect(await screen.findByText("Cô Lan")).toBeInTheDocument();
  expect(history.location.pathname).toBe("/gradebook");
  const login = calls.find((c) => c.url.endsWith("/api/auth/login/"));
  expect(login?.headers.get("X-CSRFToken")).toBe("t0ken");
});

test("signing out clears the session and returns to the login screen", async () => {
  let signedIn = true;
  const { history } = await renderApp("/", (r) => {
    if (r.url.endsWith("/api/auth/me/"))
      return signedIn ? { status: 200, body: ME } : { status: 403 };
    if (r.url.endsWith("/api/auth/logout/")) {
      signedIn = false;
      return { status: 204 };
    }
  });
  fireEvent.click(await screen.findByRole("button", { name: "Đăng xuất" }));
  await waitFor(() => expect(history.location.pathname).toBe("/login"));
  expect(screen.queryByText("Cô Lan")).not.toBeInTheDocument();
});

test("a sign-out the server refused stays signed in and says so", async () => {
  const { history } = await renderApp("/", (r) => {
    if (r.url.endsWith("/api/auth/me/")) return { status: 200, body: ME };
    if (r.url.endsWith("/api/auth/logout/")) return { status: 403 };
  });
  fireEvent.click(await screen.findByRole("button", { name: "Đăng xuất" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Chưa đăng xuất được");
  expect(history.location.pathname).toBe("/");
});

test("a server failure is no wrong password", async () => {
  await renderApp("/login", (r) =>
    r.url.endsWith("/api/auth/login/")
      ? { status: 502, body: "<html>Bad gateway</html>" }
      : undefined,
  );
  await screen.findByRole("heading", { name: "THCS Mẫu" });
  fill("Số điện thoại hoặc email", "0912000111");
  fill("Mật khẩu", "x");
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
});

test("too many attempts says to wait", async () => {
  await renderApp("/login", (r) =>
    r.url.endsWith("/api/auth/login/")
      ? { status: 429, body: { detail: "too_many_attempts" } }
      : undefined,
  );
  await screen.findByRole("heading", { name: "THCS Mẫu" });
  fill("Số điện thoại hoặc email", "0912000111");
  fill("Mật khẩu", "x");
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Đợi 15 phút");
});

test("a session that ends while signed in goes back to the login screen", async () => {
  let live = true;
  const { history, queryClient } = await renderApp("/gradebook", (r) =>
    r.url.endsWith("/api/auth/me/")
      ? live
        ? { status: 200, body: ME }
        : { status: 403 }
      : undefined,
  );
  await screen.findByText("Cô Lan");
  live = false; // signed out in another tab
  await queryClient.refetchQueries({ queryKey: ["me"] });
  await waitFor(() => expect(history.location.pathname).toBe("/login"));
  expect(history.location.search).toContain("redirect=%2Fgradebook");
  expect(screen.queryByText("Cô Lan")).not.toBeInTheDocument();
});

test("activation signs in and lands on the page asked for", async () => {
  const { history } = await renderApp("/activate?redirect=%2Fguardian", (r) => {
    if (r.url.endsWith("/api/auth/activate/")) return { status: 200, body: ME };
    if (r.url.endsWith("/api/auth/me/")) return { status: 200, body: ME };
  });
  await screen.findByRole("heading", { name: "THCS Mẫu" });
  fill("Mã mời", "ABCDE-FGHJK");
  fill("Số điện thoại hoặc email", "0912000111");
  fill("Mật khẩu", "new password 1");
  fireEvent.click(screen.getByRole("button", { name: "Kích hoạt và đăng nhập" }));
  await waitFor(() => expect(history.location.pathname).toBe("/guardian"));
});

test("activation reports a weak password under its field and a bad code once", async () => {
  let attempts = 0;
  await renderApp("/activate", (r) => {
    if (!r.url.endsWith("/api/auth/activate/")) return undefined;
    attempts += 1;
    return attempts === 1
      ? { status: 400, body: { password: ["This password is too short."] } }
      : { status: 400, body: { non_field_errors: ["Invalid or expired invitation."] } };
  });
  await screen.findByRole("heading", { name: "THCS Mẫu" });
  fill("Mã mời", "ABCDE-FGHJK");
  fill("Số điện thoại hoặc email", "0912000111");
  fill("Mật khẩu", "1");
  fireEvent.click(screen.getByRole("button", { name: "Kích hoạt và đăng nhập" }));
  expect(await screen.findByText(/Mật khẩu quá ngắn/)).toBeInTheDocument();
  expect(screen.getByLabelText("Mật khẩu")).toHaveAttribute("aria-invalid", "true");
  fireEvent.click(screen.getByRole("button", { name: "Kích hoạt và đăng nhập" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Mã mời không đúng hoặc đã hết hạn.");
});

test("redirects stay on this site", () => {
  expect(safeRedirect("/gradebook?x=1")).toBe("/gradebook?x=1");
  expect(safeRedirect("//evil.example/x")).toBeUndefined();
  expect(safeRedirect("https://evil.example")).toBeUndefined();
  expect(safeRedirect("/\\evil.example/x")).toBeUndefined();
});

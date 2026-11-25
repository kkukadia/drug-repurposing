import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { response } from "./test/fixtures";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("shows the banner before anything else", () => {
    render(<App />);
    expect(screen.getByRole("alert")).toHaveTextContent(/not medical advice/i);
  });

  it("debounces search to a single request", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMock.mockResolvedValue(jsonResponse([]));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<App />);
    await user.type(screen.getByLabelText(/search for a disease/i), "diab");
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/diseases?q=diab");
  });

  it("shows empty state when nothing matches", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText(/search for a disease/i), "zzz");
    expect(await screen.findByText(/no diseases match/i)).toBeInTheDocument();
  });

  it("shows error state on search failure", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "boom" }, 500));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText(/search for a disease/i), "diab");
    expect(await screen.findByText(/search failed: 500: boom/i)).toBeInTheDocument();
  });

  it("selects a disease, shows loading then ranked table", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/candidates")) return Promise.resolve(jsonResponse(response));
      return Promise.resolve(jsonResponse([{ disease_id: "MONDO:1", name: "Type 2 diabetes" }]));
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText(/search for a disease/i), "diab");
    await user.click(await screen.findByRole("button", { name: /Type 2 diabetes/ }));
    expect(await screen.findByText("Metformin", { exact: false })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("row").length).toBe(3));
    expect(screen.getByRole("alert")).toHaveTextContent(/API disclaimer text/);
  });

  it("shows error state when candidates fail", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/candidates"))
        return Promise.resolve(jsonResponse({ detail: "unknown disease" }, 404));
      return Promise.resolve(jsonResponse([{ disease_id: "MONDO:1", name: "Type 2 diabetes" }]));
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText(/search for a disease/i), "diab");
    await user.click(await screen.findByRole("button", { name: /Type 2 diabetes/ }));
    expect(await screen.findByText(/could not load candidates: 404/i)).toBeInTheDocument();
  });

  it("shows loading state while candidates are pending", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/candidates")) return new Promise(() => {});
      return Promise.resolve(jsonResponse([{ disease_id: "MONDO:1", name: "Type 2 diabetes" }]));
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText(/search for a disease/i), "diab");
    await user.click(await screen.findByRole("button", { name: /Type 2 diabetes/ }));
    expect(await screen.findByText(/loading candidates/i)).toBeInTheDocument();
  });
});

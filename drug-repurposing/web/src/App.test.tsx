import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { graphView, response } from "./test/fixtures";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const diseaseList = [{ disease_id: "MONDO:1", name: "Type 2 diabetes" }];

function route(overrides: { candidates?: () => Promise<Response>; graph?: () => Promise<Response> }) {
  return (url: string) => {
    if (url.includes("/candidates"))
      return (overrides.candidates ?? (() => Promise.resolve(jsonResponse(response))))();
    if (url.includes("/graph"))
      return (overrides.graph ?? (() => Promise.resolve(jsonResponse(graphView))))();
    return Promise.resolve(jsonResponse(diseaseList));
  };
}

async function pickDisease(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/search for a disease/i), "diab");
  await user.click(await screen.findByRole("button", { name: /Type 2 diabetes/ }));
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
    fetchMock.mockImplementation(route({}));
    const user = userEvent.setup();
    render(<App />);
    await pickDisease(user);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Metformin", { exact: false })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("row").length).toBe(3));
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent(/API disclaimer text/);
  });

  it("draws the relationship graph for the selected disease", async () => {
    fetchMock.mockImplementation(route({}));
    const user = userEvent.setup();
    render(<App />);
    await pickDisease(user);
    expect(
      await screen.findByRole("group", { name: /relationship graph/i }),
    ).toBeInTheDocument();
    const graphCalls = fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/graph"));
    expect(graphCalls).toHaveLength(1);
    expect(graphCalls[0]).toContain("/diseases/MONDO%3A1/graph?k=8");
  });

  it("keeps the table when the graph fails", async () => {
    fetchMock.mockImplementation(
      route({ graph: () => Promise.resolve(jsonResponse({ detail: "graph down" }, 503)) }),
    );
    const user = userEvent.setup();
    render(<App />);
    await pickDisease(user);
    expect(await screen.findByText(/could not load graph: 503/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("row").length).toBe(3));
  });

  it("keeps the graph when candidates fail", async () => {
    fetchMock.mockImplementation(
      route({ candidates: () => Promise.resolve(jsonResponse({ detail: "unknown disease" }, 404)) }),
    );
    const user = userEvent.setup();
    render(<App />);
    await pickDisease(user);
    expect(await screen.findByText(/could not load candidates: 404/i)).toBeInTheDocument();
    expect(await screen.findByRole("group", { name: /relationship graph/i })).toBeInTheDocument();
  });

  it("shows error state when candidates fail", async () => {
    fetchMock.mockImplementation(
      route({ candidates: () => Promise.resolve(jsonResponse({ detail: "unknown disease" }, 404)) }),
    );
    const user = userEvent.setup();
    render(<App />);
    await pickDisease(user);
    expect(await screen.findByText(/could not load candidates: 404/i)).toBeInTheDocument();
  });

  it("shows loading state while candidates are pending", async () => {
    fetchMock.mockImplementation(route({ candidates: () => new Promise(() => {}) }));
    const user = userEvent.setup();
    render(<App />);
    await pickDisease(user);
    expect(await screen.findByText(/loading candidates/i)).toBeInTheDocument();
  });

  it("shows loading state while the graph is pending", async () => {
    fetchMock.mockImplementation(route({ graph: () => new Promise(() => {}) }));
    const user = userEvent.setup();
    render(<App />);
    await pickDisease(user);
    expect(await screen.findByText(/loading relationship graph/i)).toBeInTheDocument();
  });
});

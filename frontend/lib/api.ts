export const resolveApiUrl = (environment: Record<string, string | undefined>) => {
  const configured = environment.NEXT_PUBLIC_API_BASE_URL || environment.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (environment.NODE_ENV !== "production") return "http://127.0.0.1:8000";
  throw new Error("NEXT_PUBLIC_API_BASE_URL is required for a production build");
};

// Next.js only embeds public variables when they are referenced explicitly.
export const API_URL = resolveApiUrl({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NODE_ENV: process.env.NODE_ENV,
});

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    cache: options.cache || "no-store",
  });
  if (!response.ok) {
    throw new Error(`API request failed (${response.status}): ${path}`);
  }
  return response.json();
}

export const percent = (value?: number | null, digits = 1) =>
  value == null ? "—" : `${(value * 100).toFixed(digits)}%`;

// Presentation-only bound: raw model values remain untouched in API responses.
export const displayProbability = (value?: number | null) => {
  if (value == null) return "—";
  const visible = Math.min(0.999, Math.max(0.001, value));
  return `${(visible * 100).toFixed(1)}%`;
};

export const number = (value?: number | null, digits = 2) =>
  value == null ? "—" : value.toFixed(digits);

export const record = (summary?: { wins: number; losses: number } | null) =>
  summary ? `${summary.wins}–${summary.losses}` : "—";

export const formatDate = (date: string) =>
  new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${date}T00:00:00Z`));

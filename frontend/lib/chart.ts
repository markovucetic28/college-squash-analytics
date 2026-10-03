function parseRatingDate(date: string) {
  return new Date(`${date}T00:00:00Z`);
}

export function formatRatingAxisDate(date: string) {
  const parsed = parseRatingDate(date);
  const month = parsed.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${month} ’${String(parsed.getUTCFullYear()).slice(-2)}`;
}

export function formatRatingTooltipDate(date: string) {
  return parseRatingDate(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export const predictionModeExplanation = (mode: string) => {
  if (mode === "verified") return "Actual official lineup is known.";
  if (mode === "projected") return "Lineup inferred from recent official lineup evidence.";
  if (mode === "preseason") return "Projection based on current roster ratings and prior lineup evidence.";
  if (mode === "team_only") return "Player-level lineup prediction unavailable; team model used instead.";
  if (mode === "custom") return "Scenario edited by you; changes are temporary and not official.";
  return "Project-generated prediction mode.";
};

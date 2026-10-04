export const estimateState = (projectable:boolean, loaded:boolean, available:boolean, loading:boolean) => {
  if (!projectable) return "team_only";
  if (loading || !loaded) return "loading";
  return available ? "available" : "unavailable";
};

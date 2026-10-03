export type LineupSlot = number | null;

export const normalizeLineup = (slots: LineupSlot[]) => {
  const players = slots.filter((player): player is number => player != null);
  return [...players, ...Array(9 - players.length).fill(null)] as LineupSlot[];
};

export const moveLineupPlayer = (slots: LineupSlot[], from: number, to: number) => {
  const active = slots.filter((player): player is number => player != null);
  if (from < 0 || to < 0 || from >= active.length || to >= active.length) return [...slots];
  const [player] = active.splice(from, 1);
  active.splice(to, 0, player);
  return normalizeLineup(active);
};

export const replaceLineupPlayer = (slots: LineupSlot[], position: number, playerId: number) => {
  if (slots.includes(playerId)) throw new Error("Player is already in the lineup");
  const next = [...slots];
  next[position] = playerId;
  return normalizeLineup(next);
};

export const removeLineupPlayer = (slots: LineupSlot[], position: number) => {
  const next = [...slots];
  next[position] = null;
  return normalizeLineup(next);
};

export const lineupChanged = (original: LineupSlot[], current: LineupSlot[]) =>
  original.some((player, index) => player !== current[index]);

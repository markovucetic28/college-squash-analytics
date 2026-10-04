const TEAM_COLORS: Record<string, string> = {
  "Amherst College": "#3f1f69", "Bates College": "#8b1e2d", "Bowdoin College": "#111111",
  "Brown University": "#4e3629", "Chatham University": "#5b2c83", "Colby College": "#1f5aa6",
  "Columbia University": "#69b3e7", "Connecticut College": "#183b6b", "Cornell University": "#b31b1b",
  "Dartmouth College": "#00693e", "Denison University": "#c8102e", "Dickinson College": "#c8102e",
  "Drexel University": "#07294d", "Franklin and Marshall College": "#0b2240", "Hamilton College": "#003087",
  "Harvard University": "#a51c30", "Haverford College": "#c41230", "Hobart College": "#ef6c00",
  "MIT": "#a31f34", "Middlebury College": "#003f2d", "Mount Holyoke College": "#003f5f",
  "Princeton University": "#e77500", "Smith College": "#003b5c", "St. Lawrence University": "#7b1e3a",
  "Stanford University": "#8c1515", "Trinity College": "#00356b", "Tufts University": "#3e8ede",
  "University of Pennsylvania": "#990000", "University of Rochester": "#003b71", "University of Virginia": "#232d4b",
  "Vassar College": "#861f41", "Wellesley College": "#003f5f", "Wesleyan University": "#d72128",
  "Western Ontario": "#4f2683", "William Smith College": "#ef6c00", "Williams College": "#512698",
  "Yale University": "#00356b",
};

export const teamColor = (team: string) => TEAM_COLORS[team] || "#526675";

export const probabilitySegments = (probability: number) => ({
  left: `${Math.max(0, Math.min(1, probability)) * 100}%`,
  right: `${Math.max(0, Math.min(1, 1 - probability)) * 100}%`,
});

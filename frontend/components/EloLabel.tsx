const explanation = "Project-defined team strength rating updated from verified match results. Higher values indicate stronger recent performance. It is not an official CSA ranking.";

export default function EloLabel() {
  return <span className="help-label" title={explanation}>Elo</span>;
}

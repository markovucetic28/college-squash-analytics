import Link from "next/link";
import { displayProbability, number, percent } from "@/lib/api";
import type { Projection } from "@/lib/types";

export default function ProjectionView({ projection, teamOne, teamTwo }: {
  projection: Projection; teamOne: string; teamTwo: string;
}) {
  if (!projection.available || !projection.pairings) {
    return <section className="notice"><strong>{projection.mode}</strong>
      {projection.team_one_probability != null && <p>Projected win probability: {teamOne} {displayProbability(projection.team_one_probability)} · {teamTwo} {displayProbability(projection.team_two_probability)}</p>}
      <p>{projection.note}</p></section>;
  }
  return <>
    <section className="prediction-summary">
      <div><span>{teamOne}</span><small>Projected win probability</small><strong>{displayProbability(projection.team_one_probability)}</strong><small>{number(projection.team_one_expected_wins)} expected wins</small></div>
      <div className="prediction-mode"><b>{projection.mode_label || projection.mode}</b><span>Lineup confidence {percent(projection.lineup_confidence, 0)}</span>{projection.data_timestamp && <span>Data through {projection.data_timestamp.slice(0,10)}</span>}</div>
      <div className="right"><span>{teamTwo}</span><small>Projected win probability</small><strong>{displayProbability(projection.team_two_probability)}</strong><small>{number(projection.team_two_expected_wins)} expected wins</small></div>
    </section>
    <p className="projection-note">{projection.note}</p>
    <div className="table-wrap pairing-table">
      <table>
        <thead><tr><th>Pos</th><th>{teamOne}</th><th>Rating</th><th>{teamOne} win probability</th><th>{teamTwo}</th><th>Rating</th></tr></thead>
        <tbody>{projection.pairings.map((pairing) => <tr key={pairing.position}>
          <td className="position">{pairing.position}</td>
          <td>{pairing.team_one_is_forfeit ? <strong>Forfeit</strong> : <><Link href={`/player/${pairing.team_one_player_id}`}>{pairing.team_one_player}</Link><small>Rating {pairing.team_one_rating_date}</small></>}</td>
          <td>{number(pairing.team_one_rating, 2)}</td>
          <td><div className={`probability-cell ${Math.abs(pairing.team_one_probability-.5)<.1 ? "close" : ""}`}><span style={{ width: `${pairing.team_one_probability * 100}%` }} />{teamOne}: {displayProbability(pairing.team_one_probability)}</div></td>
          <td>{pairing.team_two_is_forfeit ? <strong>Forfeit</strong> : <><Link href={`/player/${pairing.team_two_player_id}`}>{pairing.team_two_player}</Link><small>Rating {pairing.team_two_rating_date}</small></>}</td>
          <td>{number(pairing.team_two_rating, 2)}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </>;
}

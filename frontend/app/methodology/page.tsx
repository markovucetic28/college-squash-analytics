export default function AboutPage() {
  return (
    <article className="methodology">
      <h1>About</h1>
      <p className="lede">
        College Squash Analytics is a data and machine learning project built to make college squash results,
        rankings, player information, and match predictions easier to explore in one place.
      </p>
      <section>
        <ul className="about-list">
          <li>
            Uses historical match results, player ratings, rosters, and lineups from public College Squash
            Association / Club Locker sources.
          </li>
          <li>Includes 24,000+ individual matches and 3,500+ team matches across six seasons.</li>
          <li>
            Estimates individual player win probabilities and combines them to calculate team-level win
            probabilities.
          </li>
          <li>
            Historical evaluations avoid data leakage by using only information that would have been available
            before each match.
          </li>
          <li>
            Includes team and player pages, rankings, schedules, head-to-head comparisons, and projected matchup
            probabilities.
          </li>
        </ul>
      </section>
    </article>
  );
}

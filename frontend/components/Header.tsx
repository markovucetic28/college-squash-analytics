import Link from "next/link";
import GlobalSearch from "./GlobalSearch";
import DataFreshness from "./DataFreshness";

const links = [
  ["Schedule", "/schedule"], ["Teams", "/teams"], ["Rankings", "/rankings"],
  ["Compare", "/compare"], ["About", "/methodology"],
];

export default function Header() {
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link className="wordmark" href="/schedule"><span>CSA</span> Analytics</Link>
        <nav aria-label="Primary navigation">
          {links.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}
        </nav>
        <GlobalSearch />
        <DataFreshness />
      </div>
    </header>
  );
}

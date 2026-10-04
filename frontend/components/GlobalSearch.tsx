"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { API_URL } from "@/lib/api";
import { isExpectedAbort, nextSearchIndex } from "@/lib/search";
import type { Team } from "@/lib/types";

type PlayerResult = {
  player_id: number; name: string; canonical_team_name?: string | null;
  gender?: string | null; season?: string | null;
};

export default function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ teams: Team[]; players: PlayerResult[] }>({ teams: [], players: [] });
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults({ teams: [], players: [] });
      setOpen(false);
      setError(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/api/search?q=${encodeURIComponent(query)}`, { signal: controller.signal });
        if (response.ok) {
          const nextResults = await response.json();
          if (!controller.signal.aborted) {
            setResults(nextResults);
            setError(false);
            setOpen(true);
            setActiveIndex(-1);
          }
        }
      } catch (error) {
        if (!isExpectedAbort(error, controller.signal)) {
          setResults({ teams: [], players: [] });
          setError(true);
          setOpen(true);
        }
      }
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const hasResults = results.teams.length + results.players.length > 0;
  const resultCount = results.teams.length + results.players.length;
  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") { setOpen(false); setActiveIndex(-1); return; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault(); setOpen(hasResults); setActiveIndex((current) => nextSearchIndex(current, event.key === "ArrowDown" ? 1 : -1, resultCount));
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault(); root.current?.querySelectorAll<HTMLAnchorElement>(".search-results a")[activeIndex]?.click();
    }
  };
  return (
    <div className="global-search" ref={root}>
      <label className="sr-only" htmlFor="global-search">Search teams and players</label>
      <input id="global-search" value={query} onChange={(event) => setQuery(event.target.value)}
        onFocus={() => hasResults && setOpen(true)} onKeyDown={keyDown} placeholder="Search teams or players" autoComplete="off"
        role="combobox" aria-expanded={open} aria-controls="global-search-results" aria-activedescendant={activeIndex >= 0 ? `search-result-${activeIndex}` : undefined} />
      {open && (
        <div className="search-results" id="global-search-results" role="listbox">
          {!hasResults && <p className="search-empty">{error ? "Search is temporarily unavailable" : "No matches"}</p>}
          {results.teams.length > 0 && <p className="search-heading">Teams</p>}
          {results.teams.map((team,index) => (
            <Link id={`search-result-${index}`} role="option" aria-selected={activeIndex===index} className={activeIndex===index?"active":""} key={`${team.program_id}-${team.gender}`} href={`/team/${team.program_id}`} onClick={() => setOpen(false)}>
              <strong>{team.name}</strong><span>{team.gender === "men" ? "Men" : "Women"}</span>
            </Link>
          ))}
          {results.players.length > 0 && <p className="search-heading">Players</p>}
          {results.players.map((player,index) => {
            const itemIndex=results.teams.length+index;
            return <Link id={`search-result-${itemIndex}`} role="option" aria-selected={activeIndex===itemIndex} className={activeIndex===itemIndex?"active":""} key={player.player_id} href={`/player/${player.player_id}`} onClick={() => setOpen(false)}>
              <strong>{player.name}</strong>
              <span>{player.canonical_team_name || "Team unavailable"}, {player.gender ? `${player.gender[0].toUpperCase()}${player.gender.slice(1)}` : "Division unavailable"} ({player.season || "Season unavailable"})</span>
            </Link>;
          })}
        </div>
      )}
    </div>
  );
}

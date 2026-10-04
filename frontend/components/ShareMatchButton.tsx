"use client";

import { useState } from "react";

export default function ShareMatchButton() {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) await navigator.share({title:document.title,url});
      else await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (error) {
      if ((error as DOMException).name !== "AbortError") setCopied(false);
    }
  };
  return <button className="share-button" onClick={share}>{copied ? "Link copied" : "Share matchup"}</button>;
}

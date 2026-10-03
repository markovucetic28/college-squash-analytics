"use client";
export default function ErrorPage({reset}:{reset:()=>void}){return <section className="notice"><strong>This page could not load.</strong><p>The analytics service may be temporarily unavailable. Please <button onClick={reset}>try again</button> in a moment.</p></section>}

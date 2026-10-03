"use client";

import { useMemo, useState } from "react";
import { formatRatingAxisDate, formatRatingTooltipDate } from "@/lib/chart";

type Rating = { date: string; rating: number };

export default function RatingChart({ ratings }: { ratings: Rating[] }) {
  const [active, setActive] = useState<number | null>(null);
  const chart = useMemo(() => {
    if (ratings.length < 2) return null;
    const width = 800, height = 270, left = 64, right = 20, top = 18, bottom = 48;
    const values = ratings.map((item) => item.rating);
    const rawLow = Math.min(...values), rawHigh = Math.max(...values);
    const padding = Math.max((rawHigh - rawLow) * .12, .08);
    const low = rawLow - padding, high = rawHigh + padding;
    const x = (index: number) => left + index * (width-left-right) / (ratings.length-1);
    const y = (value: number) => top + (high-value)/(high-low) * (height-top-bottom);
    return { width,height,left,right,top,bottom,low,high,x,y,
      points:ratings.map((item,index)=>`${x(index)},${y(item.rating)}`).join(" ") };
  }, [ratings]);
  if (!chart) return <p className="muted">Not enough verified snapshots for a rating-history chart.</p>;
  const yTicks = Array.from({length:5},(_,index)=>chart.low+(chart.high-chart.low)*index/4);
  const tickCount = Math.min(5,ratings.length);
  const xIndexes = Array.from(new Set(Array.from({length:tickCount},(_,index)=>
    Math.round(index*(ratings.length-1)/Math.max(tickCount-1,1)))));
  const nearest = (clientX:number, target:SVGSVGElement) => {
    const box=target.getBoundingClientRect();
    const svgX=(clientX-box.left)/box.width*chart.width;
    const index=Math.round((svgX-chart.left)/(chart.width-chart.left-chart.right)*(ratings.length-1));
    setActive(Math.max(0,Math.min(ratings.length-1,index)));
  };
  return <div className="rating-chart-wrap">
    <svg className="chart" viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label="Official rating history" onMouseMove={(event)=>nearest(event.clientX,event.currentTarget)} onMouseLeave={()=>setActive(null)}>
      {yTicks.map((tick)=><g key={tick}><line x1={chart.left} x2={chart.width-chart.right} y1={chart.y(tick)} y2={chart.y(tick)}/><text x={chart.left-10} y={chart.y(tick)+4} textAnchor="end">{tick.toFixed(2)}</text></g>)}
      {xIndexes.map((index)=><text key={index} x={chart.x(index)} y={chart.height-20} textAnchor="middle">{formatRatingAxisDate(ratings[index].date)}</text>)}
      <text className="axis-label" transform={`translate(16 ${chart.height/2}) rotate(-90)`} textAnchor="middle">Official rating</text>
      <text className="axis-label" x={(chart.left+chart.width-chart.right)/2} y={chart.height-3} textAnchor="middle">Rating date</text>
      <polyline points={chart.points}/>
      {active != null && <g><line className="active-line" x1={chart.x(active)} x2={chart.x(active)} y1={chart.top} y2={chart.height-chart.bottom}/><circle cx={chart.x(active)} cy={chart.y(ratings[active].rating)} r="4"/><g className="chart-tooltip" transform={`translate(${Math.min(chart.x(active)+10,chart.width-165)} ${Math.max(chart.y(ratings[active].rating)-48,8)})`}><rect width="150" height="40"/><text x="8" y="16">{formatRatingTooltipDate(ratings[active].date)}</text><text x="8" y="32">Rating {ratings[active].rating.toFixed(2)}</text></g></g>}
      <rect className="chart-hit-area" x={chart.left} y={chart.top} width={chart.width-chart.left-chart.right} height={chart.height-chart.top-chart.bottom}/>
    </svg>
  </div>;
}

"use client";

import { useState } from "react";

// A generous hit target supports mouse, keyboard and touch. Tooltip stays in the SVG bounds.
export function RadarPoint({
  x,
  y,
  color,
  category,
  series,
  score,
  viewWidth = 520,
  kind,
  unit = "LV",
}: {
  x: number;
  y: number;
  color: string;
  category: string;
  series: string;
  score: number;
  viewWidth?: number;
  kind?: string;
  unit?: "LV" | "%";
}) {
  const [open, setOpen] = useState(false);
  const formatted = Number.isInteger(score) ? score : score.toFixed(1);
  const value =
    unit === "LV" ? `${series} LV ${formatted}` : `${series} ${formatted}%`;
  const left = Math.max(6, Math.min(x - 100, viewWidth - 206));
  const top = Math.max(6, y - 66);
  return (
    <g
      className="radar-point"
      role="button"
      tabIndex={0}
      aria-label={`${category}: ${value}`}
      aria-expanded={open}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={() => setOpen(true)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setOpen((value) => !value);
        }
      }}
    >
      <circle cx={x} cy={y} r="11" fill="transparent" />
      <circle
        data-series-point={kind}
        cx={x}
        cy={y}
        r="4"
        fill="white"
        stroke={color}
        strokeWidth="2.5"
        pointerEvents="none"
      />
      {open && (
        <g className="radar-point-tooltip" role="tooltip" pointerEvents="none">
          <rect
            x={left}
            y={top}
            width="200"
            height="52"
            rx="7"
            fill="#fff"
            stroke="#94a9bf"
          />
          <text x={left + 10} y={top + 19} fontSize="11" fill="#43566d">
            {category}
          </text>
          <text
            x={left + 10}
            y={top + 39}
            fontSize="13"
            fontWeight="650"
            fill="#243f53"
          >
            {value}
          </text>
        </g>
      )}
    </g>
  );
}

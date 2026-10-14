import { useEffect, useRef, useState } from 'react';

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function niceMax(v: number) {
  if (v <= 4) return 4;
  const mag = 10 ** Math.floor(Math.log10(v));
  const n = v / mag;
  return (n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag;
}

const shortDate = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

export interface Series { key: string; label: string; color: string }

/** Multi-series line chart over dates: crosshair + tooltip, legend, end labels, table view. */
export function LineChart({ data, series, title }: { data: Record<string, number | string>[]; series: Series[]; title: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const h = 240;
  const m = { t: 12, r: 72, b: 28, l: 36 };
  const iw = width - m.l - m.r;
  const ih = h - m.t - m.b;
  const max = niceMax(Math.max(1, ...data.flatMap((d) => series.map((s) => Number(d[s.key])))));
  const x = (i: number) => m.l + (data.length <= 1 ? 0 : (i / (data.length - 1)) * iw);
  const y = (v: number) => m.t + ih - (v / max) * ih;
  const ticks = [0, max / 4, max / 2, (3 * max) / 4, max];
  const labelEvery = Math.ceil(data.length / Math.max(2, Math.floor(iw / 70)));

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const box = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const px = e.clientX - box.left;
    setHover(Math.max(0, Math.min(data.length - 1, Math.round((px / box.width) * (data.length - 1)))));
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight') setHover((hv) => Math.min(data.length - 1, (hv ?? -1) + 1));
    if (e.key === 'ArrowLeft') setHover((hv) => Math.max(0, (hv ?? data.length) - 1));
  };

  // End labels: nudge apart when the two last values collide.
  const ends = series.map((s) => ({ s, y: y(Number(data[data.length - 1]?.[s.key] ?? 0)) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;

  return (
    <figure className="chart">
      <div className="chart-head">
        <figcaption>{title}</figcaption>
        <div className="legend">
          {series.map((s) => <span key={s.key}><i className="key-line" style={{ background: s.color }} />{s.label}</span>)}
          <button className="link small" onClick={() => setTable(!table)}>{table ? 'Show chart' : 'Show table'}</button>
        </div>
      </div>
      {table ? (
        <div className="table-wrap chart-table">
          <table><thead><tr><th>Date</th>{series.map((s) => <th key={s.key} className="num">{s.label}</th>)}</tr></thead>
            <tbody>{[...data].reverse().map((d) => <tr key={String(d.date)}><td>{shortDate(String(d.date))}</td>{series.map((s) => <td key={s.key} className="num">{d[s.key]}</td>)}</tr>)}</tbody></table>
        </div>
      ) : (
        <div ref={ref} className="chart-box">
          <svg width={width} height={h} role="img" aria-label={title} tabIndex={0} onKeyDown={onKey} onBlur={() => setHover(null)}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={m.l} x2={m.l + iw} y1={y(t)} y2={y(t)} className="grid" />
                <text x={m.l - 8} y={y(t)} className="axis" textAnchor="end" dominantBaseline="middle">{Math.round(t)}</text>
              </g>
            ))}
            {data.map((d, i) => i % labelEvery === 0 && (
              <text key={i} x={x(i)} y={h - 8} className="axis" textAnchor="middle">{shortDate(String(d.date))}</text>
            ))}
            {series.map((s) => (
              <polyline key={s.key} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
                points={data.map((d, i) => `${x(i)},${y(Number(d[s.key]))}`).join(' ')} />
            ))}
            {ends.map(({ s, y: ly }) => (
              <text key={s.key} x={m.l + iw + 8} y={ly} className="end-label" dominantBaseline="middle">{s.label}</text>
            ))}
            {hover != null && (
              <g>
                <line x1={x(hover)} x2={x(hover)} y1={m.t} y2={m.t + ih} className="crosshair" />
                {series.map((s) => <circle key={s.key} cx={x(hover)} cy={y(Number(data[hover][s.key]))} r={4} fill={s.color} className="dot-ring" />)}
              </g>
            )}
            <rect x={m.l} y={m.t} width={iw} height={ih} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
          </svg>
          {hover != null && (
            <div className="tooltip" style={{ left: Math.min(x(hover) + 12, width - 150), top: 8 }}>
              <div className="tooltip-title">{shortDate(String(data[hover].date))}</div>
              {series.map((s) => (
                <div key={s.key} className="tooltip-row"><i className="key-line" style={{ background: s.color }} /><strong>{data[hover][s.key]}</strong><span>{s.label}</span></div>
              ))}
            </div>
          )}
        </div>
      )}
    </figure>
  );
}

/** Horizontal bar chart, single series. */
export function BarList({ data, title, unit = '' }: { data: { label: string; value: number; sub?: string }[]; title: string; unit?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const [hover, setHover] = useState<number | null>(null);
  return (
    <figure className="chart">
      <div className="chart-head"><figcaption>{title}</figcaption></div>
      <ul className="barlist">
        {data.map((d, i) => (
          <li key={d.label} tabIndex={0} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}
            className={hover === i ? 'hover' : ''} aria-label={`${d.label}: ${d.value}${unit}`}>
            <span className="barlist-label">{d.label}</span>
            <span className="barlist-track"><span className="barlist-bar" style={{ width: `${(d.value / max) * 100}%` }} /></span>
            <span className="barlist-value">{d.value}{unit}</span>
            {hover === i && d.sub && <span className="barlist-sub">{d.sub}</span>}
          </li>
        ))}
      </ul>
    </figure>
  );
}

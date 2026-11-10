// Shared UI building blocks: flat, solid, minimal. Styles live in ui.css.
import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, Minus, Plus } from "lucide-react";
import "./ui.css";

export function Panel({ title, subtitle, actions, className = "", children }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; className?: string; children: ReactNode;
}) {
  return (
    <section className={`ui-panel ${className}`}>
      {(title || actions) && (
        <header className="ui-panel-head">
          <div>{title && <h3>{title}</h3>}{subtitle && <p>{subtitle}</p>}</div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Section({ title, action, collapsible = false, defaultOpen = true, children }: {
  title: string; action?: ReactNode; collapsible?: boolean; defaultOpen?: boolean; children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="ui-section">
      <div className="ui-section-head">
        {collapsible ? (
          <button className="ui-section-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{title}
          </button>
        ) : <span>{title}</span>}
        {action}
      </div>
      {(!collapsible || open) && children}
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "good" | "bad" }) {
  return (
    <div className="ui-stat">
      <span>{label}</span>
      <b className={tone ?? ""}>{value}</b>
    </div>
  );
}

export const StatRow = ({ children }: { children: ReactNode }) => <div className="ui-stats">{children}</div>;

export interface CompareRow { label: string; a: number; b: number; format: (v: number) => string; lowerIsBetter?: boolean }

export function CompareTable({ head, rows }: { head: [string, string]; rows: CompareRow[] }) {
  return (
    <table className="ui-table">
      <thead><tr><th /><th>{head[0]}</th><th>{head[1]}</th><th>Δ</th></tr></thead>
      <tbody>
        {rows.map(({ label, a, b, format, lowerIsBetter = true }) => {
          const pct = a ? ((b - a) / Math.abs(a)) * 100 : 0;
          const better = Math.abs(pct) < 0.05 ? "" : (pct < 0) === lowerIsBetter ? "good" : "bad";
          return (
            <tr key={label}>
              <td>{label}</td><td>{format(a)}</td><td>{format(b)}</td>
              <td className={better}>{a ? `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%` : "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="ui-toggle">
      <span><span className="ui-toggle-label">{label}</span>{hint && <small>{hint}</small>}</span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <i aria-hidden="true" />
    </label>
  );
}

export function Stepper({ label, icon, value, onChange, min = 0, max = 20 }: {
  label: string; icon?: ReactNode; value: number; onChange: (v: number) => void; min?: number; max?: number;
}) {
  return (
    <div className="ui-stepper">
      <span className="ui-stepper-label">{icon}{label}</span>
      <div className="ui-stepper-ctrl">
        <button aria-label={`Fewer ${label}`} disabled={value <= min} onClick={() => onChange(value - 1)}><Minus size={14} /></button>
        <output>{value}</output>
        <button aria-label={`More ${label}`} disabled={value >= max} onClick={() => onChange(value + 1)}><Plus size={14} /></button>
      </div>
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="ui-seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

export function ListRow({ icon, title, detail, trailing, onClick, selected }: {
  icon?: ReactNode; title: ReactNode; detail?: ReactNode; trailing?: ReactNode; onClick?: () => void; selected?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const expandable = !!detail;
  return (
    <div className={`ui-row ${selected ? "sel" : ""}`}>
      <button className="ui-row-main" onClick={() => { onClick?.(); if (expandable) setOpen(!open); }} aria-expanded={expandable ? open : undefined}>
        {icon && <span className="ui-row-icon">{icon}</span>}
        <span className="ui-row-title">{title}</span>
        {trailing && <span className="ui-row-trail">{trailing}</span>}
        {expandable && (open ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
      </button>
      {expandable && open && <div className="ui-row-detail">{detail}</div>}
    </div>
  );
}

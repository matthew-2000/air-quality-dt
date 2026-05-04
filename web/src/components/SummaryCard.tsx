import type { ReactNode } from "react";

export function SummaryCard({
  title,
  value,
  note,
  icon,
}: {
  title: string;
  value: string;
  note: string;
  icon: ReactNode;
}) {
  return (
    <article className="summary-card">
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <small>{note}</small>
      </div>
      <div className="summary-icon">{icon}</div>
    </article>
  );
}

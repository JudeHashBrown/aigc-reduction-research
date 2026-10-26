import { diffChange } from "./change-highlights.js";
import "./change-highlights.css";

/** Render precomputed diff segments as escaped React text, never HTML. */
export function ChangeHighlights({ segments = [], className = "" }) {
  return <span className={`rt-change-highlights ${className}`.trim()}>
    {segments.map((part, index) => part.kind === "removed"
      ? <del className="rt-change-removed" key={index}>{part.text}</del>
      : part.kind === "added"
        ? <ins className="rt-change-added" key={index}>{part.text}</ins>
        : <span key={index}>{part.text}</span>)}
  </span>;
}

export { diffChange };

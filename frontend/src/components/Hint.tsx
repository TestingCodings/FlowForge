/**
 * Hover explanation for non-technical users. Renders a small "?" that
 * shows a plain-language tooltip. Usage: <h3>Rules <Hint tip="…"/></h3>
 */
export default function Hint({ tip, below = false }: { tip: string; below?: boolean }) {
  return (
    <span className={below ? "hint hint-below" : "hint"} data-tip={tip} aria-label={tip} role="note">
      ?
    </span>
  );
}

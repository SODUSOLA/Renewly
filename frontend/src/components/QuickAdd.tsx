import { Link } from "react-router-dom";
import { QUICK_ADD } from "../lib/status";

// "What would you like to track?" shortcuts: each opens the add-document form already set to that kind
// of document, so a new user starts from something familiar instead of a blank form.
export function QuickAdd({ heading = "What would you like to track first?" }: { heading?: string }) {
  return (
    <div className="quick-add">
      <p className="quick-add-heading">{heading}</p>
      <ul className="chip-links">
        {QUICK_ADD.map((item) => (
          <li key={item.type}>
            <Link className="chip-link" to={`/documents?new=${item.type}`}>
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

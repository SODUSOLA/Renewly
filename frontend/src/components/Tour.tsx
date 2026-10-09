import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export interface TourStep {
  // Matches an element's data-tour attribute, e.g. data-tour="nav-reports".
  target: string;
  title: string;
  body: string;
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PADDING = 6; // breathing room around the highlighted element
const CARD_WIDTH = 340;
const SMALL_SCREEN = 640; // below this the card becomes a bottom sheet

// Finds the element for a step, but only if the user can actually see it.
function findTarget(target: string): HTMLElement | null {
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 ? el : null;
}

// True if the element (or something around it) is pinned to the screen, like a sticky header.
// Such elements are always visible, and "scrolling them into view" would only make the page jump.
function isPinned(el: HTMLElement): boolean {
  for (let node: HTMLElement | null = el; node; node = node.parentElement) {
    const position = getComputedStyle(node).position;
    if (position === "fixed" || position === "sticky") return true;
  }
  return false;
}

// Scrolls the element into view only if it isn't already comfortably on screen.
function bringIntoView(el: HTMLElement): void {
  if (isPinned(el)) return;
  const rect = el.getBoundingClientRect();
  const comfortable = rect.top >= 90 && rect.bottom <= window.innerHeight - 230;
  if (!comfortable) el.scrollIntoView?.({ block: "center", behavior: "auto" });
}

// A guided tour: dims the page, spotlights one element at a time and explains it. Steps whose
// element isn't on screen (e.g. hidden on a phone) are skipped. Keyboard: arrows move, Escape ends.
export function Tour({ steps, onClose }: { steps: TourStep[]; onClose: (finished: boolean) => void }) {
  // Only the steps that can be shown right now. Decided once the tour is on the page (it reads
  // the page, so it cannot happen while rendering); null until then.
  const [shown, setShown] = useState<TourStep[] | null>(null);
  const visible = shown ?? [];
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  // The spotlight glides between steps, but must follow the page instantly while scrolling.
  const [gliding, setGliding] = useState(false);
  const card = useRef<HTMLDivElement>(null);
  const nextButton = useRef<HTMLButtonElement>(null);
  const step = visible[index];
  const last = index === visible.length - 1;

  const close = useCallback((finished: boolean) => onClose(finished), [onClose]);

  useLayoutEffect(() => {
    setShown(steps.filter((s) => findTarget(s.target)));
  }, [steps]);

  // Nothing to show (all targets hidden): end quietly.
  useEffect(() => {
    if (shown !== null && shown.length === 0) close(false);
  }, [shown, close]);

  // Keep the spotlight on the current element, even as the page scrolls or resizes.
  useLayoutEffect(() => {
    if (!step) return;
    const el = findTarget(step.target);
    if (!el) return;
    bringIntoView(el);
    // Follow the element every frame. Scrolling and resizing are not the only things that move it:
    // content loading in above it (like the checklist appearing) pushes it down with no event at all.
    let last = "";
    let settle = 0;
    let frame = 0;
    const place = () => {
      const r = el.getBoundingClientRect();
      const key = `${r.top}|${r.left}|${r.width}|${r.height}`;
      if (key !== last) {
        last = key;
        setBox({ top: r.top - PADDING, left: r.left - PADDING, width: r.width + PADDING * 2, height: r.height + PADDING * 2 });
        // Once it stops moving, make sure it ended up somewhere the user can see it.
        window.clearTimeout(settle);
        settle = window.setTimeout(() => bringIntoView(el), 250);
      }
      frame = requestAnimationFrame(place);
    };
    place();
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
    };
  }, [step]);

  useEffect(() => {
    setGliding(true);
    const timer = window.setTimeout(() => setGliding(false), 250);
    return () => window.clearTimeout(timer);
  }, [index]);

  // Move focus into the card for each step and give it back when the tour ends.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    return () => previous?.focus?.();
  }, []);
  // The card only exists once the first spotlight position is known, so wait for that too.
  const ready = Boolean(step && box);
  useEffect(() => {
    if (ready) nextButton.current?.focus();
  }, [index, ready]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close(false);
      else if (event.key === "ArrowRight") setIndex((i) => Math.min(i + 1, visible.length - 1));
      else if (event.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close, visible.length]);

  if (!step || !box) return null;

  // Put the card below the element if there is room, otherwise above; keep it inside the screen.
  const small = window.innerWidth < SMALL_SCREEN;
  const below = box.top + box.height + 16 + 190 < window.innerHeight;
  const cardStyle = small
    ? undefined
    : {
        top: below ? box.top + box.height + 12 : Math.max(12, box.top - 12 - 190),
        left: Math.min(Math.max(12, box.left), window.innerWidth - CARD_WIDTH - 12),
        width: CARD_WIDTH,
      };

  return (
    <div className="tour" data-testid="tour">
      <div className="tour-backdrop" aria-hidden="true" />
      <div className={`tour-spot${gliding ? " tour-spot-glide" : ""}`} aria-hidden="true" style={{ top: box.top, left: box.left, width: box.width, height: box.height }} />
      <div
        className={`tour-card${small ? " tour-card-sheet" : ""}`}
        role="dialog"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        style={cardStyle}
        ref={card}
      >
        <p className="tour-progress muted small">
          Step {index + 1} of {visible.length}
        </p>
        <h2 id="tour-title">{step.title}</h2>
        <p id="tour-body">{step.body}</p>
        <div className="tour-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => close(false)}>
            Skip tour
          </button>
          <span className="tour-nav">
            {index > 0 && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setIndex(index - 1)}>
                Back
              </button>
            )}
            <button type="button" className="btn btn-primary btn-sm" ref={nextButton} onClick={() => (last ? close(true) : setIndex(index + 1))}>
              {last ? "Done" : "Next"}
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}

// The tour of the whole app, in the order a new user would meet it.
export const APP_TOUR: TourStep[] = [
  {
    target: "summary",
    title: "Your documents at a glance",
    body: "Everything is sorted into expired, expiring soon (within 30 days) and valid. Tap a card to see just those documents.",
  },
  {
    target: "add-document",
    title: "Start by adding a document",
    body: "Enter its expiry date, then pick up to four reminder days on a calendar. We email you on those days, at 8am your time.",
  },
  {
    target: "nav-documents",
    title: "All your documents",
    body: "Filter by status, type or vehicle. Open one to mark it as renewed, edit it, or see its renewal history.",
  },
  {
    target: "nav-vehicles",
    title: "Vehicles",
    body: "Add your cars so their insurance, registration and permits stay together.",
  },
  {
    target: "nav-reports",
    title: "Reports",
    body: "See what you've spent on renewals by month, type and vehicle, and download it as a spreadsheet. We also email you a summary every six months.",
  },
  {
    target: "nav-settings",
    title: "Settings",
    body: "Switch to one daily summary email, set your timezone, or turn the six-monthly report off. You can replay this tour from here any time.",
  },
];

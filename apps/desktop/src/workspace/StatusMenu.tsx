import { useEffect, useRef, useState } from "react";
import type { RequirementStatus } from "../types";
import { I } from "./icons";

// Visual treatment per requirement status, keyed by the backend enum value
// (models.py RequirementStatus). Dots match the prototype's zinc/amber/emerald.
export const STATUS: Record<RequirementStatus, { label: string; dot: string }> = {
  not_started: { label: "Not started", dot: "bg-zinc-600" },
  in_progress: { label: "In progress", dot: "bg-amber-500" },
  done: { label: "Done", dot: "bg-emerald-500" },
};

const ORDER: RequirementStatus[] = ["not_started", "in_progress", "done"];

type Props = {
  status: RequirementStatus;
  /** Human label for the requirement, used in the trigger's aria-label. */
  label: string;
  onChange: (status: RequirementStatus) => void;
  disabled?: boolean;
};

export function StatusMenu({ status, label, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Status for ${label}: ${STATUS[status].label}. Change status`}
        className="flex items-center gap-1.5 px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-300 hover:text-zinc-100 hover:border-zinc-700 transition-colors duration-150 disabled:opacity-50"
      >
        <span className={`w-1.5 h-1.5 rounded-full ${STATUS[status].dot}`} />
        <span>{STATUS[status].label}</span>
        <I.Down size={11} className="text-zinc-500" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 z-50 bg-zinc-900 border border-zinc-800 rounded shadow-xl w-36 py-1"
        >
          {ORDER.map((s) => (
            <button
              key={s}
              type="button"
              role="menuitemradio"
              aria-checked={s === status}
              onClick={() => {
                onChange(s);
                setOpen(false);
              }}
              className="w-full text-left px-2.5 py-1.5 text-[11px] text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 flex items-center gap-2 font-medium transition-colors duration-150"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS[s].dot}`} />
              {STATUS[s].label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

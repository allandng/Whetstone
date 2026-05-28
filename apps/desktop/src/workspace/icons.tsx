// Prototype icon names → lucide-react components. The reference prototype
// (design/Whetstone.reference.html) hand-drew Feather-lineage SVGs at a 1.5px
// stroke with aria-hidden; lucide gives us the same lineage, so this wrapper
// just normalises those defaults and re-exposes them under the prototype's
// short names so the ported components read 1:1 against the reference.

import {
  AlertCircle,
  Bot,
  ChevronDown,
  Clock,
  FileText,
  Mic,
  Play,
  Plus,
  Send,
  Settings,
  Square,
  User,
  X,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";

function wrap(Icon: LucideIcon) {
  return function WrappedIcon({ size = 14, strokeWidth = 1.5, ...rest }: LucideProps) {
    // aria-hidden defaults true (icons are decorative; the labelling lives on
    // the enclosing button). `...rest` after it lets a caller opt back in.
    return <Icon size={size} strokeWidth={strokeWidth} aria-hidden focusable={false} {...rest} />;
  };
}

export const I = {
  Mic: wrap(Mic),
  Play: wrap(Play),
  Stop: wrap(Square),
  Cog: wrap(Settings),
  Down: wrap(ChevronDown),
  Plus: wrap(Plus),
  Bot: wrap(Bot),
  User: wrap(User),
  Clock: wrap(Clock),
  X: wrap(X),
  Send: wrap(Send),
  File: wrap(FileText),
  Alert: wrap(AlertCircle),
};

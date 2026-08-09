"use client";

import ReactDOM from "react-dom";
import {
  cloneElement,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type PointerEvent,
  type ReactElement,
} from "react";

interface ThemedTooltipProps {
  label: string;
  children: ReactElement<{ "aria-describedby"?: string }>;
  side?: "top" | "bottom";
  className?: string;
}

interface TooltipPosition {
  left: number;
  top: number;
}

const VIEWPORT_MARGIN = 12;
const TRIGGER_GAP = 8;

export function ThemedTooltip({ label, children, side = "top", className = "" }: ThemedTooltipProps) {
  const id = useId();
  const triggerRef = useRef<HTMLSpanElement>(null);
  const bubbleRef = useRef<HTMLSpanElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suppressFocusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suppressFocusRef = useRef(false);
  const [canHover, setCanHover] = useState(false);
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const describedBy = [children.props["aria-describedby"], id].filter(Boolean).join(" ");

  function cancelClose() {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    closeTimerRef.current = null;
  }

  function scheduleClose() {
    cancelClose();
    closeTimerRef.current = setTimeout(() => setVisible(false), 120);
  }

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(hover: hover) and (pointer: fine)");
    const update = () => setCanHover(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => () => {
    cancelClose();
    if (suppressFocusTimerRef.current) clearTimeout(suppressFocusTimerRef.current);
  }, []);

  useLayoutEffect(() => {
    if (!visible) return;

    function updatePosition() {
      const trigger = triggerRef.current;
      const bubble = bubbleRef.current;
      if (!trigger || !bubble) return;
      const triggerRect = trigger.getBoundingClientRect();
      const bubbleRect = bubble.getBoundingClientRect();
      const roomAbove = triggerRect.top - VIEWPORT_MARGIN;
      const roomBelow = window.innerHeight - triggerRect.bottom - VIEWPORT_MARGIN;
      const placeAbove = side === "top"
        ? roomAbove >= bubbleRect.height + TRIGGER_GAP || roomAbove >= roomBelow
        : !(roomBelow >= bubbleRect.height + TRIGGER_GAP || roomBelow >= roomAbove);
      const idealLeft = triggerRect.left + triggerRect.width / 2 - bubbleRect.width / 2;
      const maxLeft = Math.max(VIEWPORT_MARGIN, window.innerWidth - bubbleRect.width - VIEWPORT_MARGIN);
      setPosition({
        left: Math.min(Math.max(idealLeft, VIEWPORT_MARGIN), maxLeft),
        top: placeAbove
          ? Math.max(VIEWPORT_MARGIN, triggerRect.top - bubbleRect.height - TRIGGER_GAP)
          : Math.min(window.innerHeight - bubbleRect.height - VIEWPORT_MARGIN, triggerRect.bottom + TRIGGER_GAP),
      });
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setVisible(false);
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [label, side, visible]);

  function handlePointerDown(event: PointerEvent<HTMLSpanElement>) {
    suppressFocusRef.current = event.pointerType === "touch";
    if (suppressFocusTimerRef.current) clearTimeout(suppressFocusTimerRef.current);
    if (suppressFocusRef.current) {
      suppressFocusTimerRef.current = setTimeout(() => {
        suppressFocusRef.current = false;
        suppressFocusTimerRef.current = null;
      }, 500);
    }
  }

  function handleFocus() {
    if (!suppressFocusRef.current) {
      cancelClose();
      setVisible(true);
    }
    suppressFocusRef.current = false;
    if (suppressFocusTimerRef.current) clearTimeout(suppressFocusTimerRef.current);
    suppressFocusTimerRef.current = null;
  }

  function handleBlur(event: FocusEvent<HTMLSpanElement>) {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      cancelClose();
      setVisible(false);
    }
  }

  const bubble = visible && typeof document !== "undefined" && ReactDOM.createPortal(
    <span
      ref={bubbleRef}
      id={id}
      role="tooltip"
      onMouseEnter={cancelClose}
      onMouseLeave={scheduleClose}
      className="fixed z-[60] w-max max-w-[min(15rem,calc(100vw-2rem))] rounded-md border border-brand-accent/55 bg-brand-bg px-2.5 py-2 text-center text-xs font-medium leading-snug tracking-wide text-brand-primary shadow-xl"
      style={{
        left: position?.left ?? 0,
        top: position?.top ?? 0,
        visibility: position ? "visible" : "hidden",
      }}
    >
      {label}
    </span>,
    document.body,
  );

  return (
    <>
      <span
        ref={triggerRef}
        className={`relative inline-flex ${className}`}
        onPointerDownCapture={handlePointerDown}
        onMouseEnter={() => { if (canHover) { cancelClose(); setVisible(true); } }}
        onMouseLeave={scheduleClose}
        onFocusCapture={handleFocus}
        onBlurCapture={handleBlur}
      >
        {cloneElement(children, { "aria-describedby": describedBy })}
      </span>
      {bubble}
    </>
  );
}

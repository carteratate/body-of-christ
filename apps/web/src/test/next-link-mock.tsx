// A stand-in for next/link in unit tests: `vi.mock("next/link", () => import("@/test/next-link-mock"))`.
// It follows Link's click contract — onClick first; then, for a plain left click
// that onClick didn't prevent, onNavigate and a client navigation (recorded in
// `navigations`). A modified click (cmd/ctrl/shift/alt, or not the main button)
// is left to the browser, as a new tab or window, and never calls onNavigate.
import { forwardRef, type AnchorHTMLAttributes, type MouseEvent } from "react";

export const navigations: string[] = [];
export const linkStatus = { pending: false };

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string | { pathname?: string };
  prefetch?: boolean | null | "auto";
  replace?: boolean;
  scroll?: boolean;
  onNavigate?: (event: { preventDefault: () => void }) => void;
};

const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  { href, prefetch, onNavigate, onClick, replace, scroll, children, ...props },
  ref,
) {
  void replace; // Link-only props; kept off the <a>.
  void scroll;
  const target = typeof href === "string" ? href : href.pathname ?? "";
  return (
    <a
      ref={ref}
      href={target}
      data-prefetch={prefetch === undefined || prefetch === null ? "default" : String(prefetch)}
      {...props}
      onClick={(event: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
        event.preventDefault();
        let cancelled = false;
        onNavigate?.({ preventDefault: () => { cancelled = true; } });
        if (!cancelled) navigations.push(target);
      }}
    >
      {children}
    </a>
  );
});

export function useLinkStatus() {
  return linkStatus;
}

export default Link;

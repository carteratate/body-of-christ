"use client";

import { useCallback, useTransition } from "react";
import Link, { useLinkStatus } from "next/link";
import { useRouter } from "next/navigation";
import { useIntentPrefetch } from "@/lib/useIntentPrefetch";

/**
 * A thin line, in the control's text colour, along the bottom of a control
 * while the page it opens is still on its way. It only acknowledges the click;
 * it never stands in for the destination. It fades in after 100ms (see .nav-pending in globals.css), so a
 * navigation served from a prefetch never flashes it. Its parent must be
 * positioned.
 */
export function NavPendingBar({ pending }: { pending: boolean }) {
  return (
    <span aria-hidden="true" className="nav-pending" data-pending={pending ? "true" : undefined}>
      <span />
    </span>
  );
}

function LinkPendingBar() {
  const { pending } = useLinkStatus();
  return <NavPendingBar pending={pending} />;
}

type IntentLinkProps = Omit<React.ComponentProps<typeof Link>, "prefetch"> & {
  href: string;
};

/**
 * A Link that prefetches on intent rather than on sight, and shows the pending
 * line while an unprefetched navigation is in flight. Use it for lists and
 * cards, where viewport prefetch would warm dozens of pages nobody opens.
 * Same-tab-only side effects belong in onNavigate, which a cmd/ctrl/shift or
 * middle click (a new tab or window) never calls.
 */
export function IntentLink({ href, className = "", children, ...props }: IntentLinkProps) {
  const intent = useIntentPrefetch(href);
  return (
    <Link {...props} {...intent} href={href} prefetch={false} className={`relative ${className}`}>
      {children}
      <LinkPendingBar />
    </Link>
  );
}

/**
 * For a navigation that has to stay a button (it runs a gate or resets state
 * first): push inside a transition so `pending` holds until the destination
 * commits. Render <NavPendingBar pending={pending} /> inside the button.
 */
export function usePendingNavigation() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const push = useCallback((href: string) => {
    startTransition(() => router.push(href));
  }, [router]);
  return { pending, push };
}

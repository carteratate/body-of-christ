"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "./AppShell";
import { GuestShell } from "./GuestShell";

const AUTHENTICATED_ROUTES = [
  "/search",
  "/bookmarks",
  "/history",
  "/sources",
  "/discover",
  "/settings",
  "/feedback",
  "/about",
  "/reader",
  "/chat",
];

function isRoute(pathname: string, route: string) {
  return pathname === route || pathname.startsWith(`${route}/`);
}

export function AuthenticatedRouteShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isGuestRoute = isRoute(pathname, "/search/guest") || isRoute(pathname, "/reader/guest") || isRoute(pathname, "/guest");
  const isAuthenticatedRoute = !isGuestRoute && AUTHENTICATED_ROUTES.some((route) => isRoute(pathname, route));

  if (isGuestRoute) return <GuestShell>{children}</GuestShell>;
  return isAuthenticatedRoute ? <AppShell>{children}</AppShell> : children;
}

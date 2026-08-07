import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { UserProfile } from "../types/api";

/**
 * Capability checks for the UI (docs/ROLES.md).
 *
 * These decide what to *render*. They are not security — the API enforces
 * every one of these server-side, and must keep doing so. Hiding a control
 * the user can't use is a courtesy; the check that matters is the one on the
 * server.
 *
 * The point of routing every check through here is the creator/user split:
 * an end user shouldn't be shown builder links, rule explanations, or schema
 * hints for things they can neither change nor create. Scattered role
 * literals made that impossible to apply consistently.
 *
 * The set comes from `/auth/me/`. It used to come from a role-to-capability
 * map kept in this file, which was a second copy of the backend's and was
 * written before roles were data: it only knew the five built-ins, so a
 * custom role matched nothing and its holder was shown the interface of
 * someone with no permissions at all. There is one authority now, and
 * widening a role server-side reaches the UI without a frontend change.
 */

/** Mirrors CAPABILITIES in backend/apps/accounts/models.py. */
export type Capability =
  | "workflow.view"
  | "workflow.design"    // build/edit workflows, forms, rules — the creator sphere
  | "workflow.publish"
  | "instance.view"
  | "instance.create"
  | "instance.transition"
  | "instance.approve"
  | "instance.comment"
  | "instance.metadata"
  | "instance.relate"    // re-parent, link — structural, not annotation
  | "form.submit"
  | "media.upload"
  | "media.delete"
  | "user.view"
  | "user.create"
  | "user.assign_roles"
  | "secret.manage"
  | "hook.manage"
  | "audit.view"
  | "workspace.manage";

/**
 * Pure predicate, usable outside React and easy to test.
 *
 * Fails closed on anything absent, which matches `has_capability` on the
 * backend. Notably it fails closed on an *unknown* capability too: the
 * server never reports one, so a typo at a call site hides a control rather
 * than revealing it.
 */
export function hasCapability(
  held: readonly string[] | undefined,
  capability: Capability,
): boolean {
  if (!held) return false;
  return held.includes(capability);
}

function useMe() {
  return useQuery<UserProfile>({
    queryKey: ["me"],
    queryFn: async () => (await apiClient.get("/auth/me/")).data,
    staleTime: 5 * 60 * 1000,
  });
}

export function useMyRoles(): string[] {
  return useMe().data?.roles ?? [];
}

export function useMyCapabilities(): string[] {
  return useMe().data?.capabilities ?? [];
}

/**
 * `can("workflow.design")` — true when the signed-in user holds that
 * capability. Defaults to false while the profile is loading, so a
 * creator-only control never flashes in front of an end user.
 */
export function useCan(): (capability: Capability) => boolean {
  const held = useMyCapabilities();
  return (capability: Capability) => hasCapability(held, capability);
}

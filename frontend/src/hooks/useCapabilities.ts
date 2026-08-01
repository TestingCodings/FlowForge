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
 * When roles become data (docs/ROLES.md §2) the role→capability map below is
 * replaced by a set the API returns, and callers don't change.
 */
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
  | "user.manage"
  | "secret.manage"
  | "hook.manage"
  | "audit.view"
  | "workspace.manage";

const ALL = ["platform_admin", "workflow_designer", "approver", "participant", "viewer"];
const DESIGNERS = ["platform_admin", "workflow_designer"];

const PARTICIPANT_UP = ["platform_admin", "workflow_designer", "approver", "participant"];

const CAPABILITY_ROLES: Record<Capability, string[]> = {
  "workflow.view":       ALL,
  "workflow.design":     DESIGNERS,
  "workflow.publish":    DESIGNERS,
  "instance.view":       ALL,
  "instance.create":     PARTICIPANT_UP,
  "instance.transition": PARTICIPANT_UP,
  "instance.approve":    ["platform_admin", "workflow_designer", "approver"],
  "instance.comment":    ALL,
  "instance.metadata":   PARTICIPANT_UP,
  "instance.relate":     PARTICIPANT_UP,
  "form.submit":         PARTICIPANT_UP,
  "media.upload":        PARTICIPANT_UP,
  "media.delete":        DESIGNERS,
  "user.view":           ALL,
  "user.manage":         ["platform_admin"],
  "secret.manage":       DESIGNERS,
  "hook.manage":         DESIGNERS,
  "audit.view":          DESIGNERS,
  "workspace.manage":    ["platform_admin"],
};

/**
 * Pure predicate, usable outside React and easy to test.
 *
 * Fails closed on a capability this map does not know, matching
 * `has_capability` on the backend. It previously indexed the map directly and
 * threw a TypeError instead, so a typo at a call site would have taken the
 * page down rather than hiding one control.
 */
export function roleHas(roles: string[], capability: Capability): boolean {
  const permitted = CAPABILITY_ROLES[capability];
  if (!permitted) return false;
  return roles.some((r) => permitted.includes(r));
}

export function useMyRoles(): string[] {
  const { data } = useQuery<UserProfile>({
    queryKey: ["me"],
    queryFn: async () => (await apiClient.get("/auth/me/")).data,
    staleTime: 5 * 60 * 1000,
  });
  return data?.roles ?? [];
}

/**
 * `can("workflow.design")` — true when the signed-in user holds a role with
 * that capability. Defaults to false while the profile is loading, so a
 * creator-only control never flashes in front of an end user.
 */
export function useCan(): (capability: Capability) => boolean {
  const roles = useMyRoles();
  return (capability: Capability) => roleHas(roles, capability);
}

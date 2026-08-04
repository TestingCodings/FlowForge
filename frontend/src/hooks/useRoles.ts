import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { Role } from "../types/api";

/**
 * Every role on this install, most senior first.
 *
 * Read from the API rather than a constant, because roles are data now: a
 * hardcoded list would silently omit whatever the client has defined, which
 * is the whole point of the feature. `ALL_ROLES` in types/api.ts remains only
 * as a fallback label source for the built-in five.
 */
export function useRoles() {
  return useQuery<Role[]>({
    queryKey: ["roles"],
    queryFn: async () => {
      const { data } = await apiClient.get("/roles/?page_size=200");
      return (data.results ?? data) as Role[];
    },
    staleTime: 60_000,
  });
}

/**
 * The highest rank the signed-in user holds.
 *
 * Nobody may assign a role more senior than their own, and the API enforces
 * that. Knowing it here lets the UI disable those options rather than letting
 * someone pick one and receive a 403.
 */
export function maxRank(roles: Role[], held: string[]): number {
  return roles
    .filter((r) => held.includes(r.key))
    .reduce((top, r) => Math.max(top, r.rank), 0);
}

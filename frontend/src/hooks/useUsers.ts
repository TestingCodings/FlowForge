import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { UserProfile } from "../types/api";

/**
 * Every active user.
 *
 * A single hook because the cache key is shared. AppLayout (for the demo
 * switcher) and the users page both read `["users"]`, and they previously
 * declared their own queries with *different* return shapes: one unwrapped
 * `.results` to an array, the other returned the paginated object whole.
 * Whichever mounted last won the cache, so opening the users page replaced
 * AppLayout's array with an object and `allUsers.filter(...)` threw, taking
 * down the entire tree including the sidebar. The page had never once
 * rendered.
 *
 * Sharing one hook makes that class of mismatch impossible: there is only one
 * declaration of what `["users"]` holds.
 */
export function useUsers() {
  return useQuery<UserProfile[]>({
    queryKey: ["users"],
    queryFn: async () => {
      const { data } = await apiClient.get("/users/?page_size=200");
      return (data.results ?? data) as UserProfile[];
    },
  });
}

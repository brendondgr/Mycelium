import type { ProfileData } from "@/lib/portal/types";

export type CompletenessItem = {
  label: string;
  done: boolean;
};

export type Completeness = {
  percent: number;
  items: CompletenessItem[];
  doneCount: number;
  total: number;
};

/**
 * A transparent profile-completeness score derived from the fields we actually
 * have — so the "grow my profile" nudge reflects the signed-in user, not a fixed
 * mock percentage. Each item maps to something Milo uses for matching.
 */
export function computeCompleteness(
  profile: ProfileData | undefined,
): Completeness {
  const interests = profile?.interests ?? { version: 1, areas: [] };
  const items: CompletenessItem[] = [
    {
      label: "Research areas",
      done: (interests.areas?.length ?? 0) > 0,
    },
    {
      label: "Research statement",
      done: Boolean(interests.statement && interests.statement.trim()),
    },
    {
      label: "Keywords",
      done: (interests.keywords?.length ?? 0) > 0,
    },
    {
      label: "Institution",
      done: Boolean(profile?.institution && profile.institution.trim()),
    },
    {
      label: "Linked publication source",
      done: Boolean(
        profile?.orcid || profile?.openalex_id || profile?.scholar_id,
      ),
    },
  ];

  const doneCount = items.filter((item) => item.done).length;
  const total = items.length;
  return {
    items,
    doneCount,
    total,
    percent: total ? Math.round((doneCount / total) * 100) : 0,
  };
}

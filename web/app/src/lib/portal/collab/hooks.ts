"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchCollaborationPreview,
  fetchCollaborationSetting,
  fetchSavedPeople,
  fetchSearchAvailability,
  saveCollaborationSetting,
} from "./client";

const SETTING_KEY = ["collab", "setting"] as const;
const PREVIEW_KEY = ["collab", "preview"] as const;

export function useCollaborationSetting() {
  return useQuery({ queryKey: SETTING_KEY, queryFn: fetchCollaborationSetting });
}

export function useCollaborationPreview(enabled: boolean) {
  return useQuery({ queryKey: PREVIEW_KEY, queryFn: fetchCollaborationPreview, enabled });
}

export function useSaveCollaborationSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveCollaborationSetting,
    onSuccess: (setting) => {
      queryClient.setQueryData(SETTING_KEY, setting);
    },
  });
}

/** Whether this person may search for collaborators, and how widely. */
export function useSearchAvailability() {
  return useQuery({
    queryKey: ["collab", "availability"],
    queryFn: fetchSearchAvailability,
    staleTime: 5 * 60 * 1000,
  });
}

export function useSavedPeople(enabled: boolean) {
  return useQuery({ queryKey: ["collab", "saved"], queryFn: fetchSavedPeople, enabled });
}

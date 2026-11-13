"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  answerSuggestion,
  deleteObservations,
  deleteUnderstanding,
  editUnderstanding,
  fetchAmbientSettings,
  fetchChanges,
  fetchLabChanges,
  fetchOrgServers,
  fetchRecording,
  fetchProjectDevelopments,
  fetchSuggestions,
  fetchUnderstanding,
  reopenUnderstanding,
  saveAmbientSettings,
  saveOrgServer,
  saveRecording,
  undoChange,
} from "./client";

const ROOT = ["ambient"] as const;

/** Everything on the page moves together: an answer changes the feed, the
 * understanding and the counts at once. */
function useInvalidateAmbient() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ROOT });
}

export function useSuggestions() {
  return useQuery({ queryKey: [...ROOT, "suggestions"], queryFn: fetchSuggestions });
}

export function useAnswerSuggestion() {
  const invalidate = useInvalidateAmbient();
  return useMutation({
    mutationFn: ({ id, choice, correction }: { id: number; choice: string; correction?: string }) =>
      answerSuggestion(id, { choice, correction }),
    onSuccess: () => invalidate(),
  });
}

export function useChanges() {
  return useQuery({ queryKey: [...ROOT, "changes"], queryFn: fetchChanges });
}

export function useUndoChange() {
  const invalidate = useInvalidateAmbient();
  return useMutation({ mutationFn: undoChange, onSuccess: () => invalidate() });
}

export function useUnderstanding() {
  return useQuery({ queryKey: [...ROOT, "understanding"], queryFn: fetchUnderstanding });
}

export function useEditUnderstanding() {
  const invalidate = useInvalidateAmbient();
  return useMutation({
    mutationFn: ({ conceptId, relation, label }: { conceptId: number; relation: string; label: string }) =>
      editUnderstanding(conceptId, relation, label),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteUnderstanding() {
  const invalidate = useInvalidateAmbient();
  return useMutation({
    mutationFn: ({ conceptId, relation }: { conceptId: number; relation: string }) =>
      deleteUnderstanding(conceptId, relation),
    onSuccess: () => invalidate(),
  });
}

export function useReopenUnderstanding() {
  const invalidate = useInvalidateAmbient();
  return useMutation({
    mutationFn: ({ conceptId, relation }: { conceptId: number; relation: string }) =>
      reopenUnderstanding(conceptId, relation),
    onSuccess: () => invalidate(),
  });
}

export function useAmbientSettings() {
  return useQuery({ queryKey: [...ROOT, "settings"], queryFn: fetchAmbientSettings });
}

export function useSaveAmbientSettings() {
  const invalidate = useInvalidateAmbient();
  return useMutation({ mutationFn: saveAmbientSettings, onSuccess: () => invalidate() });
}

export function useDeleteObservations() {
  const invalidate = useInvalidateAmbient();
  return useMutation({ mutationFn: deleteObservations, onSuccess: () => invalidate() });
}

export function useProjectDevelopments(projectId: string | null) {
  return useQuery({
    queryKey: [...ROOT, "developments", projectId],
    queryFn: () => fetchProjectDevelopments(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useLabChanges(slug: string | null) {
  return useQuery({
    queryKey: [...ROOT, "lab-changes", slug],
    queryFn: () => fetchLabChanges(slug as string),
    enabled: Boolean(slug),
  });
}

/** What Mylo records of me, per server and per project. */
export function useRecording() {
  return useQuery({ queryKey: [...ROOT, "recording"], queryFn: fetchRecording });
}

export function useSaveRecording() {
  const invalidate = useInvalidateAmbient();
  return useMutation({ mutationFn: saveRecording, onSuccess: () => invalidate() });
}

/** An org's Discord servers and the head's listening switch for each. */
export function useOrgServers(kind: "lab" | "department", ref: string) {
  return useQuery({
    queryKey: [...ROOT, "org-servers", kind, ref],
    queryFn: () => fetchOrgServers(kind, ref),
  });
}

export function useSaveOrgServer(kind: "lab" | "department", ref: string) {
  const invalidate = useInvalidateAmbient();
  return useMutation({
    mutationFn: (body: { guild_id: string; on: boolean }) => saveOrgServer(kind, ref, body),
    onSuccess: () => invalidate(),
  });
}

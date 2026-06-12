// AgentX — Global State Store (Zustand)
import { create } from 'zustand';
import type { ProgressEvent, RunDetail, RunListItem } from '@/types';

interface RunStore {
  // Run list
  runs: RunListItem[];
  setRuns: (runs: RunListItem[]) => void;

  // Active run
  activeRunId: string | null;
  setActiveRunId: (id: string | null) => void;
  activeRun: RunDetail | null;
  setActiveRun: (run: RunDetail | null) => void;

  // Progress
  progressEvents: ProgressEvent[];
  addProgressEvent: (event: ProgressEvent) => void;
  clearProgressEvents: () => void;

  // UI
  isSubmitting: boolean;
  setIsSubmitting: (v: boolean) => void;
}

export const useRunStore = create<RunStore>((set) => ({
  runs: [],
  setRuns: (runs) => set({ runs }),

  activeRunId: null,
  setActiveRunId: (id) => set({ activeRunId: id, progressEvents: [] }),
  activeRun: null,
  setActiveRun: (run) => set({ activeRun: run }),

  progressEvents: [],
  addProgressEvent: (event) =>
    set((state) => ({
      progressEvents: [...state.progressEvents.slice(-200), event],
    })),
  clearProgressEvents: () => set({ progressEvents: [] }),

  isSubmitting: false,
  setIsSubmitting: (v) => set({ isSubmitting: v }),
}));

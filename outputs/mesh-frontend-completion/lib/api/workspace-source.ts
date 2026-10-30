import type { Dataset } from "@/lib/api/dataset";
/** The demo adapter registers its live state after store creation, avoiding initialization cycles. */
let read: ((org: string) => Partial<Dataset> | null) | undefined;
let subscribe: ((notify: () => void) => () => void) | undefined;
let snapshot: (() => unknown) | undefined;
export function registerWorkspaceSource(source: { read: NonNullable<typeof read>; subscribe: NonNullable<typeof subscribe>; snapshot: NonNullable<typeof snapshot> }) {
  read = source.read; subscribe = source.subscribe; snapshot = source.snapshot;
}
export const readWorkspace = (org: string) => read?.(org) ?? null;
export const subscribeWorkspace = (notify: () => void) => subscribe?.(notify) ?? (() => {});
export const workspaceSnapshot = () => snapshot?.() ?? null;
export const serverWorkspaceSnapshot = () => null;

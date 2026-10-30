import { create } from "zustand";
export interface IntegrationDraft { id: string; org: string; actor: string; target: string; subject: string; body: string; at: string }
interface Drafts { drafts: IntegrationDraft[]; save: (draft: Omit<IntegrationDraft, "id" | "at">) => string }
/** Integration-ready local drafts. No external transmission or authentication credentials. */
export const useDrafts = create<Drafts>((set) => ({ drafts: [], save: (draft) => {
  if (!draft.org || !draft.actor || !draft.target || draft.subject.trim().length < 3 || draft.subject.length > 200 || draft.body.trim().length < 10 || draft.body.length > 5000) throw new Error("Enter a subject of 3–200 characters and a message of 10–5000 characters.");
  const id = crypto.randomUUID();
  set((s) => ({ drafts: [{ ...draft, id, at: new Date().toISOString() }, ...s.drafts] }));
  return id;
} }));

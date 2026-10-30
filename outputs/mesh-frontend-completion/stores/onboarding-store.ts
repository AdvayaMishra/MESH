import { create } from "zustand";

interface OnboardingState {
  companyName: string;
  ownerName: string;
  email: string;
  website: string;
  industry: string;
  size: string;
  verificationCode: string;
  emailVerified: boolean;
  /** Result of the *simulated* domain check. Never represents a real lookup. */
  domainCheck: "idle" | "checking" | "simulated-pass";
  set: (p: Partial<Omit<OnboardingState, "set">>) => void;
}

export function makeVerificationCode(seed: string) {
  let h = 7;
  for (const c of seed || "mesh") h = (h * 33 + c.charCodeAt(0)) >>> 0;
  return `mesh-verify=${h.toString(36)}${(h >>> 3).toString(36)}a9f2`.slice(0, 30);
}

export const useOnboarding = create<OnboardingState>((set) => ({
  companyName: "",
  ownerName: "",
  email: "",
  website: "",
  industry: "",
  size: "",
  verificationCode: "",
  emailVerified: false,
  domainCheck: "idle",
  set: (p) => set(p),
}));

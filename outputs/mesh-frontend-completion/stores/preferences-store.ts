import { administration } from "@/stores/admin-store";
import { tenants } from "@/lib/api/mock";
import { create } from "zustand";
import type { Role } from "@/lib/types";

type Profile = { name: string; email: string; role: string };
const actorFor = (org: string, role: Role, employeeId?: string): string => employeeId ?? usePreferences.getState().personas[org]?.[role] ?? tenants[org]?.roleUsers[role] ?? "unknown";
const keyFor = (org: string, role: Role, employeeId?: string) => JSON.stringify([org, role, actorFor(org, role, employeeId)]);
interface Preferences {
  personas: Record<string, Partial<Record<Role, string>>>;
  selectPersona: (org: string, role: Role, employeeId: string) => void;
  profiles: Record<string, Profile>;
  photos: Record<string, string>;
  savePhoto: (org: string, role: Role, data: string, employeeId?: string) => void;
  supportDrafts: Record<string, string>;
  saveSupportDraft: (org: string, role: Role, message: string) => void;
  preferences: Record<string, Record<string, boolean>>;
  saveProfile: (org: string, role: Role, profile: Profile, employeeId?: string) => string | null;
  setPreference: (org: string, role: Role, name: string, value: boolean) => void;
}
/** Demo session state only; never stores credentials or claims to configure a provider. */
export const usePreferences = create<Preferences>((set) => ({
  personas: {}, selectPersona: (org, role, employeeId) => { const employee = administration(org).employees.find((e) => e.id === employeeId && e.appRole === role); if (!employee) throw new Error("Persona must belong to this organization and role"); set((s) => ({ personas: { ...s.personas, [org]: { ...s.personas[org], [role]: employeeId } } })); },
  photos: {}, savePhoto: (org, role, data, employeeId) => {
    if (!administration(org).employees.some((e) => e.id === actorFor(org, role, employeeId) && e.appRole === role)) throw new Error("Profile identity must belong to this organization and role");
    if (data !== "" && (!/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(data) || data.length > 2800000)) throw new Error("Invalid profile image");
    set((s) => ({ photos: { ...s.photos, [keyFor(org, role, employeeId)]: data } }));
  },
  profiles: {}, preferences: {}, supportDrafts: {},
  saveSupportDraft: (org, role, message) => set((s) => ({ supportDrafts: { ...s.supportDrafts, [keyFor(org, role)]: message } })),
  saveProfile: (org, role, profile, employeeId) => {
    if (!administration(org).employees.some((e) => e.id === actorFor(org, role, employeeId) && e.appRole === role)) return "Profile identity must belong to this organization and role.";
    const clean = { name: profile.name.trim(), email: profile.email.trim(), role: profile.role.trim() };
    if (clean.name.length < 2 || clean.name.length > 100) return "Enter a name between 2 and 100 characters.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(clean.email) || clean.email.length > 254) return "Enter a valid email address.";
    if (!clean.role || clean.role.length > 100) return "Enter a title up to 100 characters.";
    set((s) => ({ profiles: { ...s.profiles, [keyFor(org, role, employeeId)]: clean } }));
    return null;
  },
  setPreference: (org, role, name, value) => set((s) => ({ preferences: { ...s.preferences, [keyFor(org, role)]: { ...s.preferences[keyFor(org, role)], [name]: value } } })),
}));
export { keyFor as preferenceKey };

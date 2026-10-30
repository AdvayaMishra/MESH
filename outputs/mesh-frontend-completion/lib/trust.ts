/**
 * Trust Stars scoring model (decision support only).
 *  - Score is 0–50 points; one star per 10 points (so 20 points = 2 stars).
 *  - Eligible developer/security roles start at 20 points.
 *  - Scores only change through reviewed events; they never trigger adverse employee actions automatically.
 */
import type { Employee, Role, TrustEvent } from "@/lib/types";

export const TRUST_MIN = 0;
export const TRUST_MAX = 50;
export const TRUST_START = 20;
export const POINTS_PER_STAR = 10;
/** Reviewed events may move the score by at most this many points at once. */
export const TRUST_MAX_DELTA = 5;

const ELIGIBLE_ROLES: Role[] = ["senior-dev", "junior-dev", "security-analyst"];
const ELIGIBLE_DEPARTMENTS = ["Engineering", "Infrastructure", "Security"];

export const isTrustEligible = (e: Pick<Employee, "appRole" | "department">) =>
  ELIGIBLE_ROLES.includes(e.appRole) && ELIGIBLE_DEPARTMENTS.includes(e.department);

export const clampScore = (n: number) => Math.min(TRUST_MAX, Math.max(TRUST_MIN, Math.round(n)));
export const scoreFromEvents = (events: Pick<TrustEvent, "delta">[]) => clampScore(TRUST_START + events.reduce((a, e) => a + e.delta, 0));
export const wholeStars = (score: number) => Math.floor(clampScore(score) / POINTS_PER_STAR);
export const describeTrust = (score: number) => `${score} / ${TRUST_MAX} points · ${wholeStars(score)} ${wholeStars(score) === 1 ? "star" : "stars"}`;

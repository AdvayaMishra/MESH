import { Badge } from "@/components/ui/badge";
import type { EmploymentStatus, VerificationStatus } from "@/lib/types";

export function StatusBadge({ status }: { status: EmploymentStatus }) {
  const tone = { Active: "mint", "On leave": "sky", Onboarding: "violet", Offboarding: "coral", Probation: "amber" } as const;
  return <Badge tone={tone[status]} dot>{status}</Badge>;
}

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const tone = { Verified: "mint", "Pending review": "amber", "Needs resubmission": "coral", "Not submitted": "neutral" } as const;
  return <Badge tone={tone[status]} dot>{status}</Badge>;
}

import { PageHeader } from "@/components/features/page-header";
import { EmployeeAdministration } from "@/components/features/people/administration";
export default function AdministrationPage() { return <div className="space-y-6"><PageHeader title="Employee administration" description="Onboarding, lifecycle, departments and roles within the active demonstration organization." /><EmployeeAdministration /></div>; }

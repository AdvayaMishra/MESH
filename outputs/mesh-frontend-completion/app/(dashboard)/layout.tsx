import { TooltipProvider } from "@/components/ui/tooltip";
import { PreviewDashboard } from "@/components/connected/dashboard";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider>
      <PreviewDashboard>{children}</PreviewDashboard>
    </TooltipProvider>
  );
}

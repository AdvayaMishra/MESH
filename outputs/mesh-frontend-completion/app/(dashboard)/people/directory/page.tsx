"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { Download, Eye, MoreHorizontal, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { Select } from "@/components/ui/input";
import { DataTable } from "@/components/ui/data-table";
import { Dropdown, DropdownContent, DropdownItem, DropdownTrigger } from "@/components/ui/dropdown";
import { StatusBadge, VerificationBadge } from "@/components/features/people/shared";
import { Skeleton } from "@/components/ui/skeleton";
import { useApi } from "@/hooks/use-api";
import { IntegrationDraft } from "@/components/features/integration-draft";
import { api } from "@/lib/api";
import { downloadCsv } from "@/lib/export/csv";
import { fmtDate } from "@/lib/utils/format";
import type { Employee } from "@/lib/types";

export default function DirectoryPage() {
  const router = useRouter();
  const [messageTo, setMessageTo] = React.useState<string | null>(null);
  const { data, loading } = useApi(() => api.employees());
  const [dept, setDept] = React.useState("all");
  const [status, setStatus] = React.useState("all");
  const [search, setSearch] = React.useState("");

  const rows = (data ?? []).filter((e) => (dept === "all" || e.department === dept) && (status === "all" || e.status === status));

  const exportedRows = rows.filter((e) => JSON.stringify(e).toLowerCase().includes(search.toLowerCase()));
  const columns = React.useMemo<ColumnDef<Employee, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Employee",
        cell: ({ row: { original: e } }) => (
          <div className="flex items-center gap-3">
            <Avatar name={e.name} size={34} />
            <div className="min-w-0"><p className="truncate font-medium text-ink">{e.name}</p><p className="truncate text-xs text-ink-3">{e.email}</p></div>
          </div>
        ),
      },
      { accessorKey: "id", header: "Employee ID", cell: ({ getValue }) => <span className="font-mono text-xs text-ink-2">{String(getValue())}</span> },
      { accessorKey: "department", header: "Department" },
      { accessorKey: "role", header: "Role" },
      { accessorKey: "status", header: "Status", cell: ({ row }) => <StatusBadge status={row.original.status} /> },
      { accessorKey: "verification", header: "Verification", cell: ({ row }) => <VerificationBadge status={row.original.verification} /> },
      { accessorKey: "joinDate", header: "Joined", cell: ({ getValue }) => fmtDate(String(getValue()), { month: "short", day: "numeric", year: "numeric" }) },
      {
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        enableSorting: false,
        cell: ({ row }) => (
          <div onClick={(e) => e.stopPropagation()}>
            <Dropdown>
              <DropdownTrigger asChild><Button variant="ghost" size="iconSm" aria-label={`Actions for ${row.original.name}`}><MoreHorizontal /></Button></DropdownTrigger>
              <DropdownContent>
                <DropdownItem icon={<Eye />} onSelect={() => router.push(`/people/directory/${row.original.id}`)}>View profile</DropdownItem>
                <DropdownItem onSelect={() => setMessageTo(row.original.email)}>Draft message</DropdownItem>
                <DropdownItem onSelect={() => router.push("/people/lifecycle")}>Change access</DropdownItem>
              </DropdownContent>
            </Dropdown>
          </div>
        ),
      },
    ],
    [router]
  );

  const depts = Array.from(new Set((data ?? []).map((e) => e.department))).sort();

  return (
    <div>
      <PageHeader
        title="Employee directory"
        description="Everyone in the organization, with their role, status and verification state."
        actions={
          <>
            <Button variant="secondary" disabled={!exportedRows.length} onClick={() => { downloadCsv("mesh-employees-demo.csv", ["Employee ID", "Name", "Email", "Department", "Role", "Status", "Verification", "Joined"], exportedRows.map((e) => [e.id, e.name, e.email, e.department, e.role, e.status, e.verification, e.joinDate])); toast.success("Demo directory CSV downloaded", { description: "Includes all matching records across pages." }); }}><Download /> Export</Button>
            <Button variant="gradient" asChild><Link href="/people/lifecycle"><UserPlus /> Onboard employee</Link></Button>
          </>
        }
      />
      <Card>
        {loading ? (
          <div className="space-y-3 p-5">{Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Search by name, ID, role or email"
            onRowClick={(e) => router.push(`/people/directory/${e.id}`)}
            filters={
              <>
                <Select aria-label="Filter by department" value={dept} onChange={(e) => setDept(e.target.value)} className="!h-10 w-44">
                  <option value="all">All departments</option>
                  {depts.map((d) => <option key={d}>{d}</option>)}
                </Select>
                <Select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="!h-10 w-40">
                  <option value="all">All statuses</option>
                  {["Active", "On leave", "Onboarding", "Probation", "Offboarding"].map((s) => <option key={s}>{s}</option>)}
                </Select>
              </>
            }
          />
        )}
      </Card>
      <IntegrationDraft open={!!messageTo} onOpenChange={(open) => !open && setMessageTo(null)} target={messageTo ?? ""} title="Employee message draft" />
    </div>
  );
}

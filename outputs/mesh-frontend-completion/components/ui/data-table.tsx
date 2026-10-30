"use client";
import * as React from "react";
import {
  type ColumnDef, type SortingState, flexRender, getCoreRowModel, getFilteredRowModel, getPaginationRowModel, getSortedRowModel, useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils/cn";

export function DataTable<T>({
  data,
  columns,
  searchPlaceholder = "Search…",
  filters,
  pageSize = 8,
  onRowClick,
  empty = "No results match your filters.",
  toolbar,
  search,
  onSearchChange,
}: {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  searchPlaceholder?: string;
  filters?: React.ReactNode;
  pageSize?: number;
  onRowClick?: (row: T) => void;
  empty?: string;
  toolbar?: React.ReactNode;
  search?: string;
  onSearchChange?: (value: string) => void;
}) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [localFilter, setLocalFilter] = React.useState("");
  const globalFilter = search ?? localFilter;
  const setGlobalFilter = onSearchChange ?? setLocalFilter;
  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: (updater) => setGlobalFilter(typeof updater === "function" ? updater(globalFilter) : updater),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
    globalFilterFn: (row, _id, value: string) => JSON.stringify(row.original).toLowerCase().includes(value.toLowerCase()),
  });
  const rows = table.getRowModel().rows;

  return (
    <div>
      <div className="flex flex-col gap-3 border-b border-line p-4 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-3" />
          <input
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="h-10 w-full rounded-xl border border-line-strong bg-white pl-10 pr-3 text-sm placeholder:text-ink-3 focus:border-violet focus:outline-none focus:ring-4 focus:ring-violet/15"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">{filters}</div>
        {toolbar}
      </div>
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-[13.5px]">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-line bg-canvas/70 text-xs text-ink-2">
                {hg.headers.map((h) => {
                  const sortable = h.column.getCanSort();
                  const dir = h.column.getIsSorted();
                  return (
                    <th key={h.id} className="px-4 py-3 font-medium" aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none"}>
                      {h.isPlaceholder ? null : sortable ? (
                        <button className="inline-flex items-center gap-1 hover:text-ink" onClick={h.column.getToggleSortingHandler()}>
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          {dir === "asc" ? <ArrowUp className="size-3.5" /> : dir === "desc" ? <ArrowDown className="size-3.5" /> : <ChevronsUpDown className="size-3.5 opacity-50" />}
                        </button>
                      ) : (
                        flexRender(h.column.columnDef.header, h.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr
                key={r.id}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={() => onRowClick?.(r.original)}
                onKeyDown={(e) => e.key === "Enter" && onRowClick?.(r.original)}
                className={cn("transition-colors hover:bg-tint-violet/40", onRowClick && "cursor-pointer")}
              >
                {r.getVisibleCells().map((c) => (
                  <td key={c.id} className="px-4 py-3">{flexRender(c.column.columnDef.cell, c.getContext())}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState title="Nothing to show" description={empty} />}
      </div>
      <div className="flex items-center justify-between border-t border-line px-4 py-3 text-xs text-ink-2">
        <span>
          {table.getFilteredRowModel().rows.length} result{table.getFilteredRowModel().rows.length === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <span>Page {table.getState().pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}</span>
          <Button size="iconSm" variant="secondary" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()} aria-label="Previous page"><ChevronLeft /></Button>
          <Button size="iconSm" variant="secondary" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()} aria-label="Next page"><ChevronRight /></Button>
        </div>
      </div>
    </div>
  );
}

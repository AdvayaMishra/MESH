import type { Dataset } from "@/lib/api/dataset";
import { lumen } from "./lumen";
import { northwind } from "./northwind";

/** Registry of simulated tenants. Add a dataset here and it appears in the organization switcher. */
export const tenants: Record<string, Dataset> = { lumen, northwind };
export const tenantList = Object.values(tenants);
export const DEFAULT_ORG_ID = "lumen";

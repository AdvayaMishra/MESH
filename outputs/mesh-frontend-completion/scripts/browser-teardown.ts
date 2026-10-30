import { writeFileSync } from "node:fs";
export default function teardown() { writeFileSync(`.test-server-${process.env.E2E_PORT || "3120"}.stop`, "stop owned test server"); }

import {writeFileSync} from "node:fs";
import {resolve} from "node:path";
export default function teardown(){writeFileSync(".test-server-3100.stop","stop owned connected test server");writeFileSync(resolve("../../work/final-integration-test.stop"),"stop owned backend fixture");}

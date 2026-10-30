import {readFile,writeFile,copyFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
const source=new URL("../../mesh/docs/openapi.json",import.meta.url);
const frontend=new URL("../",import.meta.url);
const api=JSON.parse(await readFile(source,"utf8"));
if(!api.openapi?.startsWith("3.")||!api.paths?.["/api/v1/users/me"]||!api.components?.schemas)throw new Error("Expected MESH OpenAPI contract");
const operations=[];
for(const [path,methods] of Object.entries(api.paths)){
 if(!/^\/(?:[A-Za-z0-9_-]+|\{[A-Za-z0-9_]+\})(?:\/(?:[A-Za-z0-9_-]+|\{[A-Za-z0-9_]+\}))*$/.test(path))throw new Error("Unsupported contract path");
 for(const [method,op] of Object.entries(methods)){
  if(!["get","post","put","patch","delete"].includes(method))continue;
  operations.push({path,method:method.toUpperCase(),title:op.summary??"",description:op.description??"",parameters:op.parameters??[],body:op.requestBody??null,authenticated:Boolean((op.security??api.security??[]).length)});
 }
}
await writeFile(new URL("lib/connected/contract.json",frontend),JSON.stringify({operations,schemas:api.components.schemas})+"\n");
await copyFile(source,new URL("docs/backend-openapi.json",frontend));
console.log(`Synchronized ${operations.length} operations from ${fileURLToPath(source)}; no services contacted.`);

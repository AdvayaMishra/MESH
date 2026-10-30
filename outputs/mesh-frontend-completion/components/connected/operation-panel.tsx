"use client";
import { useEffect, useRef, useState } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { ApiError, request } from "@/lib/connected/client";
import contract from "@/lib/connected/contract.json";

export interface Schema { $ref?: string; type?: string; format?: string; title?: string; description?: string; enum?: (string | number)[]; anyOf?: Schema[]; properties?: Record<string, Schema>; required?: string[]; default?: unknown; minimum?: number; maximum?: number; minLength?: number; maxLength?: number; pattern?: string; }
export interface Operation { path: string; method: string; title: string; description: string; parameters: {name:string;in:string;required?:boolean;schema:Schema}[]; body: {required?:boolean;content?:Record<string,{schema:Schema}>}; authenticated: boolean; }
export const operations = contract.operations as unknown as Operation[];
export function resolve(schema: Schema): Schema {
  if (schema.$ref) return resolve((contract.schemas as unknown as Record<string, Schema>)[schema.$ref.split("/").pop()!] || {});
  if (schema.anyOf) return resolve(schema.anyOf.find(s => s.type === "string") || schema.anyOf.find(s => s.type !== "null") || {});
  return schema;
}
const title = (s: string) => s.replaceAll("_", " ").replace(/^./, v => v.toUpperCase());
function display(value: unknown): string { return value === null ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value); }
export function Result({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (!value.length) return <p className="rounded-xl bg-canvas p-4 text-sm text-ink-2">No records returned. This view contains no seeded demo records.</p>;
    if (value.every(v => v && typeof v === "object" && !Array.isArray(v))) {
      const keys = [...new Set(value.flatMap(v => Object.keys(v)))].slice(0, 9);
      return <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr>{keys.map(k => <th className="border-b p-3" key={k}>{title(k)}</th>)}</tr></thead><tbody>{value.map((v, i) => <tr className="border-b" key={v.id || i}>{keys.map(k => <td className="max-w-64 break-words p-3 align-top" key={k}>{display(v[k])}</td>)}</tr>)}</tbody></table><p className="mt-2 text-xs text-ink-3">{value.length} returned records. Use the limit/offset fields for another page.</p></div>;
    }
  }
  return <pre className="max-h-[36rem] overflow-auto whitespace-pre-wrap break-all rounded-xl bg-canvas p-4 text-xs" aria-label="Backend result">{JSON.stringify(value, null, 2)}</pre>;
}
export function OperationPanel({ operation, organization, onSession }: { operation: Operation; organization?: string; onSession?: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [file, setFile] = useState<File>();
  const [result, setResult] = useState<unknown>(undefined);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current=true; return () => { active.current=false; }; }, []);
  const bodySchema = resolve(operation.body.content?.["application/json"]?.schema || {});
  const parameters = operation.parameters.filter(p => p.in !== "header");
  const fields = [
    ...parameters.map(p => ({ key: p.in + ":" + p.name, name: p.name, schema: resolve(p.schema), required: !!p.required })),
    ...Object.entries(bodySchema.properties || {}).map(([name,schema]) => ({key:"body:"+name,name,schema:resolve(schema),required:bodySchema.required?.includes(name) || false})),
  ];
  const upload = !!operation.body.content && !operation.body.content["application/json"];
  function valueFor(key: string, schema: Schema): string {
    if (key in values) return values[key];
    if (schema.default !== undefined && schema.default !== null) return typeof schema.default === "object" ? JSON.stringify(schema.default) : String(schema.default);
    return "";
  }
  function convert(value: string, schema: Schema): unknown {
    if (schema.format === "date-time") return new Date(value).toISOString();
    if (schema.type === "integer" || schema.type === "number") { const n=Number(value); if (!Number.isFinite(n)) throw new Error("Enter a finite number"); return n; }
    if (schema.type === "boolean") return value === "true";
    if (["array","object"].includes(schema.type || "")) return JSON.parse(value);
    return value;
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(""); setResult(undefined); active.current=true;
    try {
      let path=operation.path; const query=new URLSearchParams(); const body:Record<string,unknown>={};
      for (const field of fields) {
        const value=valueFor(field.key,field.schema);
        if (!value && !field.required) continue;
        if (field.key.startsWith("path:")) path=path.replace("{"+field.name+"}",encodeURIComponent(value));
        else if (field.key.startsWith("query:")) query.set(field.name,value);
        else body[field.name]=convert(value,field.schema);
      }
      if (query.size) path += "?"+query;
      if (upload && (!file || !["image/jpeg","image/png"].includes(file.type) || file.size>2097152)) throw new Error("Choose a JPEG or PNG no larger than 2 MiB");
      const response = await request(path,operation.method,upload ? file : operation.body.content ? body : undefined,organization);
      if (active.current) { setResult(response); if (response && typeof response==="object" && "session_created" in response) onSession?.(); }
    } catch (e) { if (active.current) setError(e instanceof ApiError ? `${e.message} (${e.status})${e.requestId ? " · Request "+e.requestId : ""}` : e instanceof Error ? e.message : "Request failed"); }
    finally { if(active.current) setBusy(false); }
  }
  // A tenant/user switch unmounts this keyed panel. Late results cannot populate another workspace.
  return <div><Card><CardHeader title={operation.title} subtitle={operation.method === "GET" ? "Read from the connected backend" : "Submit a real backend operation"} /><CardBody>
    {operation.description && <p className="mb-4 text-sm text-ink-2">{operation.description}</p>}
    <form className="space-y-4" onSubmit={submit}>
      <div className="grid gap-4 md:grid-cols-2">{fields.map(field => {
        const s=field.schema, value=valueFor(field.key,s), id="field-"+field.key;
        const props={id,value,required:field.required,onChange:(e:React.ChangeEvent<HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement>)=>setValues(v=>({...v,[field.key]:e.target.value}))};
        return <Field key={field.key} htmlFor={id} label={title(field.name)+(field.required ? " *" : "")} hint={s.description || (s.format === "uuid" ? "Use the actual UUID returned by the backend" : undefined)}>
          {s.enum || s.type === "boolean" ? <Select {...props}><option value="">{field.required ? "Choose…" : "Default / not supplied"}</option>{(s.enum || ["true","false"]).map(v=><option key={String(v)} value={String(v)}>{String(v)}</option>)}</Select>
          : ["object","array"].includes(s.type || "") ? <Textarea {...props} placeholder={s.type === "array" ? "[]" : "{}"} />
          : <div className="flex gap-2"><Input {...props} type={/password|token|secret/.test(field.name) ? "password" : s.format === "date" ? "date" : s.format === "date-time" ? "datetime-local" : ["integer","number"].includes(s.type || "") ? "number" : "text"} step="any" min={s.minimum} max={s.maximum} minLength={s.minLength} maxLength={s.maxLength} placeholder={s.format === "uuid" ? "00000000-0000-0000-0000-000000000000" : undefined} />{field.name === "request_key" && <Button type="button" variant="secondary" onClick={()=>setValues(v=>({...v,[field.key]:crypto.randomUUID()}))}>Generate</Button>}</div>}
        </Field>;
      })}</div>
      {upload && <Field label="Identity image · JPEG/PNG · maximum 2 MiB"><Input aria-label="Identity image" type="file" accept="image/jpeg,image/png" required onChange={e=>setFile(e.target.files?.[0])} /><p className="text-xs text-ink-3">Use fictional test documents only. No automatic approval or deletion is implied.</p></Field>}
      {operation.method !== "GET" && <p className="rounded-xl bg-tint-amber p-3 text-sm">This action saves a real change. Check the selected organization and identifiers. External actions require their configured services; submission is not proof of completion.</p>}
      <Button variant="gradient" disabled={busy}>{busy ? "Waiting for backend…" : operation.method === "GET" ? "Load records" : "Submit change"}</Button>
      {error && <p role="alert" className="break-words rounded-xl bg-tint-coral p-3 text-sm">{error}</p>}
    </form>
    {result !== undefined && <section className="mt-6" aria-live="polite"><h3 className="mb-3 font-semibold">Backend response</h3><Result value={result} /></section>}
  </CardBody></Card></div>;
}

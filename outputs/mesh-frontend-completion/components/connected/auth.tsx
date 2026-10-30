"use client";
import { Turnstile } from "@/components/connected/turnstile";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/features/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { request } from "@/lib/connected/client";
import { usePreviewInfo } from "@/lib/connected/use-preview-info";

type Mode="login"|"register"|"verify"|"recover"|"password";
export function ConnectedAuth({mode="login"}:{mode?:Mode}) {
  const router=useRouter();
  const preview=usePreviewInfo();
  const [sandboxRole,setSandboxRole]=useState("owner");
  const [email,setEmail]=useState(""),[password,setPassword]=useState(""),[code,setCode]=useState(""),[captcha,setCaptcha]=useState(""),[kind,setKind]=useState("signup");
  const [attempt,setAttempt]=useState(0);
  const needsCaptcha=["login","register","recover"].includes(mode);
  const [ownerName,setOwnerName]=useState("");
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(""),[error,setError]=useState("");
  const titles={login:"Sign in to MESH",register:"Create your account",verify:"Verify your email",recover:"Recover your account",password:"Set your password"};
  async function submit(e:React.FormEvent) {
    e.preventDefault();if(busy)return;if(needsCaptcha&&!captcha){setError("Complete the bot verification first.");return;}setBusy(true);setError("");setMessage("");
    try {
      const paths={login:"login",register:"register",verify:"verify",recover:"recover",password:"password"};
      const body=mode==="verify"?{email,token:code,type:kind}:mode==="password"?{password}:mode==="recover"?{email,captcha_token:captcha}:{email,password,captcha_token:captcha,...(mode==="register"?{owner_name:ownerName}:{})};
      await request("/api/v1/auth/"+paths[mode],mode==="password"?"PUT":"POST",body);
      if(mode==="login" || mode==="verify") {sessionStorage.setItem("mesh-preview-mode","connected");if(mode==="verify"&&kind==="recovery")router.push("/reset-password");else router.push("/workspace");}
      else setMessage(preview.mode==="local_sandbox"?(mode==="register"?"Registration submitted to the local fixture; no email was sent and no hosted account was created.":"Request handled by the local fixture; no external identity operation was performed."):mode==="register"?"Registration submitted. Check your actual inbox, then open Verify email. Delivery and expiry depend on the configured provider.":mode==="recover"?"Recovery submitted. If accepted by the configured provider, check your inbox and verify with recovery selected.":"Password updated successfully. Sign in with your new password.");
    }catch(e){setError(e instanceof Error?e.message:"Request failed");}finally{setBusy(false);setCaptcha("");setAttempt(n=>n+1);}
  }
  return <AuthShell simulated={false} title={titles[mode]} subtitle={preview.mode==="local_sandbox"?"Local sandbox · synthetic identities · isolated test database":preview.mode==="connected"?"Connected preview · actual backend authentication":"Checking preview mode…"} footer={<div className="flex flex-wrap justify-center gap-3"><Link href="/login">Sign in</Link><Link href="/register">Register</Link><Link href="/register/verify">Verify email</Link><Link href="/forgot-password">Recovery</Link><Link href="/mfa">Authenticator</Link></div>}>
    {preview.dedicated_accounts_available&&mode==="login"&&<div className="mb-6 space-y-3 rounded-2xl bg-tint-mint p-4"><p className="text-sm"><strong>Dedicated preview accounts.</strong> These are approved fictional users with real Supabase sessions. Changes are saved in the isolated preview organization.</p><Select aria-label="Dedicated preview role" value={sandboxRole} onChange={e=>setSandboxRole(e.target.value)}>{["owner","hr","senior_developer","junior_developer","security_analyst"].map(r=><option key={r} value={r}>{r.replaceAll("_"," ")}</option>)}</Select><Button variant="gradient" disabled={busy||!captcha} onClick={async()=>{setBusy(true);setError("");try{const response=await fetch("/api/preview-login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({role:sandboxRole,captcha_token:captcha})});const value=await response.json();if(!response.ok)throw new Error(value?.error?.message||"Preview sign-in failed");localStorage.setItem("mesh-connected-organization",preview.organization_id!);sessionStorage.setItem("mesh-preview-mode","connected");router.push("/workspace");}catch(e){setError(e instanceof Error?e.message:"Preview sign-in failed");}finally{setBusy(false);setCaptcha("");setAttempt(n=>n+1);}}}>Open dedicated preview account</Button></div>}
    {preview.mode==="local_sandbox"&&mode==="login"&&<div className="mb-6 space-y-3 rounded-2xl bg-tint-amber p-4"><p className="text-sm">Explore real backend workflows using fictional accounts. Authentication is substituted locally; no Supabase, email, scanner, OCR, SCIM or AWS integration is verified by this sandbox.</p><Select aria-label="Sandbox role" value={sandboxRole} onChange={e=>setSandboxRole(e.target.value)}>{["owner","hr","senior_developer","junior_developer","security_analyst"].map(r=><option key={r} value={r}>{r.replaceAll("_"," ")}</option>)}</Select><Button variant="gradient" disabled={busy} onClick={async()=>{setBusy(true);setError("");try{await request("/api/v1/auth/login","POST",{email:sandboxRole+"@example.invalid",password:"fixture-password-only",captcha_token:"fixture-only"});localStorage.setItem("mesh-connected-organization",preview.organization_id!);sessionStorage.setItem("mesh-preview-mode","connected");router.push("/workspace");}catch(e){setError(e instanceof Error?e.message:"Sandbox unavailable");}finally{setBusy(false);setCaptcha("");setAttempt(n=>n+1);}}}>Open local sandbox</Button></div>}
    <form className="space-y-4" onSubmit={submit}>
      {mode==="register"&&<Field label="Your full name" htmlFor="owner-name"><Input id="owner-name" value={ownerName} onChange={e=>setOwnerName(e.target.value)} required minLength={1} maxLength={200} autoComplete="name" /></Field>}
      {mode!=="password" && <Field label="Email" htmlFor="email"><Input id="email" type="email" value={email} onChange={e=>setEmail(e.target.value)} required autoComplete="username" /></Field>}
      {["login","register","password"].includes(mode)&&<Field label="Password" htmlFor="password"><Input id="password" type="password" minLength={12} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} required autoComplete={mode==="login"?"current-password":"new-password"} /></Field>}
      {mode==="verify"&&<><Field label="Email code" htmlFor="code"><Input id="code" value={code} onChange={e=>setCode(e.target.value)} minLength={6} maxLength={10} required autoComplete="one-time-code" /></Field><Field label="Verification type"><Select aria-label="Verification type" value={kind} onChange={e=>setKind(e.target.value)}><option value="signup">Signup</option><option value="recovery">Recovery</option></Select></Field></>}
      {(needsCaptcha||mode==="verify")&&<Turnstile onToken={setCaptcha} attempt={attempt} />}
      {needsCaptcha&&process.env.NEXT_PUBLIC_MESH_CAPTCHA_CHECK==="true"&&<Button type="button" disabled={busy||!captcha} onClick={async()=>{setBusy(true);setError("");setMessage("");try{const response=await fetch("/api/turnstile-check",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({captcha_token:captcha})});const data=await response.json();if(!response.ok)throw new Error(data.message||"CAPTCHA check failed");setMessage(data.message);}catch(e){setError(e instanceof Error?e.message:"CAPTCHA check failed");}finally{setBusy(false);setCaptcha("");setAttempt(n=>n+1);}}}>Verify CAPTCHA setup</Button>}
      {mode==="verify"&&kind==="signup"&&<Button type="button" variant="secondary" disabled={busy||!captcha||!email} onClick={async()=>{setBusy(true);setError("");setMessage("");try{await request("/api/v1/auth/resend","POST",{email,captcha_token:captcha});setMessage("If eligible, a fresh confirmation code has been requested. Check your inbox and respect the resend cooldown.");}catch(e){setError(e instanceof Error?e.message:"Resend failed");}finally{setBusy(false);setCaptcha("");setAttempt(n=>n+1);}}}>Resend confirmation code</Button>}
      <Button variant="gradient" className="w-full" disabled={busy||(needsCaptcha&&!captcha)}>{busy?"Contacting backend…":titles[mode]}</Button>
      {error&&<p role="alert" className="rounded-xl bg-tint-coral p-3 text-sm">{error}</p>}{message&&<p role="status" className="rounded-xl bg-tint-mint p-3 text-sm">{message}</p>}
    </form>
    <p className="mt-5 text-center text-xs text-ink-3">No shared demo password. <Link className="underline" href="/demo-login">Explore the separate simulated frontend</Link></p>
  </AuthShell>;
}

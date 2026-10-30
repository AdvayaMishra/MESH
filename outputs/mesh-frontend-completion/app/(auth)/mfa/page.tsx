import Link from "next/link";
import {LiveMfa} from "@/lib/connected/mfa";
export default function Page(){return <main className="mx-auto max-w-2xl space-y-6 px-4 py-10"><h1 className="font-display text-2xl font-bold">Verify your account</h1><p className="text-sm text-ink-2">After signing in, verify your authenticator before opening a workspace that requires MFA.</p><LiveMfa/><div className="flex gap-4 text-sm"><Link className="underline" href="/workspace">Continue to workspace</Link><Link className="underline" href="/login">Sign in</Link></div></main>;}

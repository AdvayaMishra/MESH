# Frontend completion matrix

> Current connected checkpoint —29October2026: final frontend integration is implemented and locally verified. Default mode uses existing backend APIs; the older demo-only descriptions and test counts below are historical. Build/types pass, lint0errors/6warnings,11Node tests and22connected browser tests pass; backend regression1,280passed/32skipped. Live hosted acceptance is blocked by this session's outgoing database socket restriction (Windows10013), not missing Supabase configuration. See [the current integration guide](docs/FINAL_BACKEND_INTEGRATION.md) and [machine results](verification/final-integration-summary.json). Unsupported/missing backend capabilities remain explicitly unavailable.

Updated from actual implementation and the release run completed at 2026-10-28T15:54:35.374Z. This is a verified demonstration frontend; live backend/provider execution is listed separately below.

| Module | Feature | Initial state | Implemented result | Verification |
|---|---|---|---|---|
| OWNER | Organization identity and domain UI | Read-only identity | Owner edits name/domain; domain remains explicitly unverified in the demo | Administration logic; browser organization journey |
| OWNER | Departments and budgets | Seeded department charts | Editable monthly USD allocations, cent validation and audit | Administration/resource logic; budget browser journey |
| OWNER | Project portfolio and approvals | Seeded proposals and decisions | Shared proposal, endorsement and owner-decision history | Review/repository logic; route audit |
| OWNER | Resource allocation | Seeded project members | Owner/senior member allocation synchronized with employee profiles | Resource allocation logic; project route audit |
| OWNER | Finance, cloud costs and exports | Seeded financial charts | Finance views, CSV/XLSX and print/PDF export; actual provider collection remains external | Unit/source/build; finance routes and browser planning journey |
| OWNER | Free-text What-If | Preset and percentage model | Explainable cloud-spend arithmetic with assumptions; rejects negative/ambiguous inputs | Model tests; free-text browser journey |
| PEOPLE | Employee onboarding and administration | Directory without create/update workflow | Validated employee creation, lifecycle status, department and owner-controlled role edits | Administration logic; employee creation browser journey |
| PEOPLE | Directory, profiles and search/export | Seeded directory and local filters | Shared current records, department counts, memberships and filtered CSV | Tenant logic; browser directory/tenant journeys |
| PEOPLE | ID submission and review | Disconnected upload preview/review queue | Synthetic submission enters review queue; decisions update directory; activation requires review | Review/second-audit logic; complete invitation browser journey |
| PEOPLE | Lifecycle approval and reversal | Animated preview with success-only save | Saved plans, independent approval, guarded execution and reversal of demo status | Lifecycle logic; complete lifecycle browser journey |
| PEOPLE | Leave and self-service | Existing validation/state actions | Request, cancel, calendar, dedicated review inbox, self-decision prohibition | 143 HR checks; leave browser journeys |
| PEOPLE | Payroll review and approval | Component-local review state | Shared discrepancy review/Finance flag, preparation and independent approval | Resource/payroll logic; payroll browser journey |
| PEOPLE | Promotions | Existing proposal state machine | Validated proposals and independent decisions/withdrawal; no automatic pay/access change | HR logic; promotion browser journeys |
| PEOPLE | Confidential complaints | Existing private case state machines | Own cases, restricted HR review, assignment, escalation, messages, internal notes and closure | HR logic and complaint browser journeys |
| PEOPLE | Sensitive data visibility | Notification and audit metadata gaps | Role/recipient notification filtering; private case metadata excluded from shared audit/feed/export | Confidential audit and notification regression checks; role/tenant browser tests |
| DEVTRACK | Projects and proposals | Existing demo views | Validated proposals, endorsements, owner decisions and current-state lookups | Review/repository/second-audit logic; project routes |
| DEVTRACK | Task CRUD and comments | Creation/deletion checks but unguarded edits/comments | Role/tenant/identity/date/field validation, comments, deletion protection and audit | Task/completion logic; full task CRUD browser journey |
| DEVTRACK | Kanban, backlog and assignment | Existing board/list | Current shared task state, filters, assignment and CSV; progress updates with task state | Task/resource logic; board and task browser journeys |
| DEVTRACK | Sprints | Existing planning source | Create/start/complete, active-sprint validation, points and task selectors | Sprint logic; sprint route audit |
| DEVTRACK | Labels, priorities, points and dates | Existing forms | Bounded edits, valid enum/date/sprint checks and synchronized task details | Task and completion regression suites |
| DEVTRACK | PR review and simulated merge | Existing demo workflow | Assigned/independent reviews, passing-check requirement, justification and duplicate prevention | Repository workflow logic; PR route audit |
| DEVTRACK | Repository authorization and scanning UI | Animation without retained run history | Owner authorization, recorded simulated runs, duplicate rejection and saved history | Repository/second-audit logic; security route audit |
| DEVTRACK | Finding remediation | Shared finding state | Assignment/status validation; junior risk acceptance denied; current findings across views | Security logic; security browser routes |
| DEVTRACK | Developer analytics and Trust Stars | Some fabricated per-person contribution counts | Task/PR counts from current records; unavailable commits identified; reviewed 0â€“50 whole-star scores | Tenant/Trust logic; performance route audit |
| DEVTRACK | Activity and exports | Seeded activity and CSV | Current shared actions and safe CSV downloads; centralized reports also support XLSX and print/PDF | Source/unit/browser route and workflow coverage |
| VADER | Overview, telemetry and risk | Seeded security dashboards | Current incidents/findings plus clearly seeded historical telemetry/risk illustrations | Security/tenant logic; VADER/risk/behavior route audit |
| VADER | Incident lifecycle and investigation | Status controls without retained analyst notes | Investigation status, saved notes, correlated evidence and audit | Security logic; investigation browser journey |
| VADER | Response approval and reversal | Existing action state | Known-action validation, actor permissions, justification, duplicate protection and reversal | Security logic; complete response/reversal browser journey |
| VADER | Attack-chain exploration | Interactive seeded graph | Graph selection, evidence details and replay retained; no claimed live correlation | Attack-chain/incident route audit and visual checks |
| VADER | Cloud assets and IAM posture | Seeded provider inventory | Provider filtering, exposure/permission findings, resource owners and explained remediation | Cloud route audit; cloud browser journey |
| VADER | Cloud remediation and ticket UI | Component-local done state and unavailable ticket toast | Saved remediation/reopen state and usable local ticket drafts | Completion logic; remediation browser journey |
| VADER | Vulnerability management and reports | Seeded findings and reports | Current finding/incident exports in CSV/XLSX/print-PDF, date filters, investigation links and role restrictions | Security/repository logic; report/security routes |
| VADER | Free-text Copilot | Keyword/preset grounded demo | Active-tenant evidence references, unsupported-query handling and no unsupported causal claims | Assistant grounding logic; free-text browser journey |
| SHARED | Demo authentication/onboarding | Form/step previews | Validated demonstration flows, ID review gate and consistent activated persona | Authentication routes; full invitation browser journey |
| SHARED | Tenant/role state and navigation | Existing two-tenant state | Unknown tenant rejection, state isolation, role-remounted subtrees and scoped quick actions | 212 tenant checks; complete role/tenant browser matrix |
| SHARED | Global search | Existing command palette | Current projects/incidents; permission-filtered routes/people; real report navigation | Role/tenant browser matrix; command palette source audit |
| SHARED | Notifications, activity and audit | Role filtering and consistency gaps | Recipient/module filtering, current actions and private case redaction; filtered exports | Privacy regressions; notification/role/browser journeys |
| SHARED | Profile, photo and settings | Success-only profile save and unavailable photo | Shared profile, validated local photos/removal and per-tenant/role preferences | Preferences logic; profile/photo browser journeys |
| SHARED | Messages/support/ticket interfaces | Success-only or unavailable toasts | Validated, saved, scoped drafts with copy behavior; no external-send claim | Source/types/build and affected route audit |
| SHARED | Dialogs, keyboard and errors | Existing Radix components and synchronous confirmation | Awaited confirmation, duplicate suppression, visible errors and accurate clipboard results | Browser workflows/role navigation and responsive checks |
| SHARED | Responsive design | Premium source without current browser verification | Original palette/layout retained; mobile/tablet/desktop checks across all modules | Module visual checks at 390/768/1440 plus settings checks |
| ARCHITECTURE | API contracts and credentials | Unused typed HTTP transport | Typed demo models, confirmed OpenAPI snapshot, tenant-race/redirect protection; no privileged credentials | API boundary unit checks; integration guide |
| RELEASE | Verification and packaging | Uncompiled/unverified supplied checkpoint | Seven gated checks, unchanged-source fingerprints, reports and clean source archive | verification/results.json and browser-summary.json |

## Route inventory

Every page below passed compilation. Non-dynamic routes were also opened in the route audit. Dynamic project, employee and incident screens are covered by scoped route/workflow tests; the generic route crawl does not invent IDs.

| Source | Verification |
|---|---|
| `app/(auth)/forgot-password/page.tsx` | Compilation and browser route audit |
| `app/(auth)/invite/employee/activate/page.tsx` | Compilation and browser route audit |
| `app/(auth)/invite/employee/id-upload/page.tsx` | Compilation and browser route audit |
| `app/(auth)/invite/employee/page.tsx` | Compilation and browser route audit |
| `app/(auth)/invite/employee/pending/page.tsx` | Compilation and browser route audit |
| `app/(auth)/invite/hr/page.tsx` | Compilation and browser route audit |
| `app/(auth)/login/page.tsx` | Compilation and browser route audit |
| `app/(auth)/register/dns/page.tsx` | Compilation and browser route audit |
| `app/(auth)/register/organization/page.tsx` | Compilation and browser route audit |
| `app/(auth)/register/page.tsx` | Compilation and browser route audit |
| `app/(auth)/register/pending/page.tsx` | Compilation and browser route audit |
| `app/(auth)/register/verify/page.tsx` | Compilation and browser route audit |
| `app/(auth)/register/website/page.tsx` | Compilation and browser route audit |
| `app/(auth)/reset-password/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/devtrack/board/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/devtrack/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/devtrack/projects/[id]/page.tsx` | Compilation and related workflow/role coverage |
| `app/(dashboard)/devtrack/projects/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/devtrack/pull-requests/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/devtrack/security/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/devtrack/sprints/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/owner/finance/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/owner/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/owner/performance/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/owner/projects/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/administration/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/complaints/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/directory/[id]/page.tsx` | Compilation and related workflow/role coverage |
| `app/(dashboard)/people/directory/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/leave/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/leave/review/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/lifecycle/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/payroll/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/promotions/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/people/verification/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/attack-chain/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/behavior/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/cloud/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/copilot/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/incidents/[id]/page.tsx` | Compilation and related workflow/role coverage |
| `app/(dashboard)/vader/incidents/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/risk/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/vader/simulation/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/activity/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/audit/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/complaints/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/help/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/leave/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/notifications/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/organization/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/reports/page.tsx` | Compilation and browser route audit |
| `app/(dashboard)/workspace/settings/page.tsx` | Compilation and browser route audit |
| `app/(marketing)/page.tsx` | Compilation and browser route audit |

## Live dependencies outside this frontend delivery

Supabase authentication/email/CAPTCHA/MFA, durable database persistence, private Storage/antivirus/OCR, GitHub App installation/merges, actual scanner workers, cloud collection/changes, SCIM, payments, external messaging/ticketing and hosted model calls require backend/provider configuration and acceptance. No live adapter is enabled in this source. The older connected preview remains a separate implementation.

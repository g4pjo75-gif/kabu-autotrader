# CCAGI Agents

このプロジェクトで利用可能なエージェント一覧。
各エージェントはCCAGI MCPサーバーを通じて実行されます。

| Agent | Description | 実行方法 |
|-------|-------------|----------|
| ai-product-analyzer | AI product profiler. Inspects a repo and emits structured product profile (surface, model integrations, prompts, eval, license). Read-only with citations. | `agent_run(name: "ai-product-analyzer")` |
| aiproductanalyzer | GitHubリポジトリからAIプロダクトを分析・抽出するAgent | `agent_run(name: "aiproductanalyzer")` |
| api | API contract design agent. Owns the OpenAPI/GraphQL document, versioning, and backward-compat report. Does not implement handlers. | `agent_run(name: "api")` |
| architecture | Architecture design agent. Owns component diagram, interface map, technology choice rationale, non-functional budget, and ADRs. Does not implement. | `agent_run(name: "architecture")` |
| aws-agent | AWS read-only advisory agent. Owns cost estimates, optimization findings, account audits, service catalog lookups, citations. Never mutates AWS state. | `agent_run(name: "aws-agent")` |
| aws | AWS Agent - Cloud Infrastructure Management, Budget/Cost Management, Cost Estimation, Resource Optimization. Enterprise tier。 .ccagi/knowledge/ からAWSサービスカタログ・料金・re:Invent情報を参照。 CCI活用でコードベースのAWS利用実態を調査（fallback: grep）。 | `agent_run(name: "aws")` |
| backend | Backend implementation agent. Produces server endpoints, persistence access, workers, and tests for a specified feature, plus a verify checklist. | `agent_run(name: "backend")` |
| batch-issue | Batch issue creation agent. Reads template + variable rows, emits DryRun/Apply/Sync report. Read-only by default; respects label registry and rate limits. | `agent_run(name: "batch-issue")` |
| batchissue | GitHub Issue一括作成Agent - テンプレートからバッチ作成 + Headless実行対応 | `agent_run(name: "batchissue")` |
| browser-automation | Browser automation agent. Drives a real browser through a scenario, emits structured run report (steps, screenshots, network/console captures, assertions). Read-only on backend. | `agent_run(name: "browser-automation")` |
| ci-controller | CI/CD orchestration controller. Gates ops via 7 invariants (PR merge / runner / workflow / deploy / secrets / OIDC / smoke). Leads deployment + devops + deploy-infra + ci-runner-mgmt swarm. | `agent_run(name: "ci-controller")` |
| ci-runner-mgmt | Self-hosted runner specialist. Health monitoring + capacity + container lifecycle + image cleanup. ProtectActiveJob + RequireAckForLifecycle. Read-only by default. | `agent_run(name: "ci-runner-mgmt")` |
| codegen | AI-driven source code generation agent (Claude Sonnet) | `agent_run(name: "codegen")` |
| codex-codegen | OpenAI Codex駆動コード生成Agent | `agent_run(name: "codex-codegen")` |
| codex-docs | OpenAI Codex駆動ドキュメントAgent | `agent_run(name: "codex-docs")` |
| codex-refactor | OpenAI Codex駆動リファクタリングAgent | `agent_run(name: "codex-refactor")` |
| codex-test | OpenAI Codex駆動テストAgent | `agent_run(name: "codex-test")` |
| codexcodegen | OpenAI Codex駆動コード生成Agent | `agent_run(name: "codexcodegen")` |
| codexdocs | OpenAI Codex駆動ドキュメントAgent | `agent_run(name: "codexdocs")` |
| codexrefactor | OpenAI Codex駆動リファクタリングAgent | `agent_run(name: "codexrefactor")` |
| codextest | OpenAI Codex駆動テストAgent | `agent_run(name: "codextest")` |
| coordinator | Task orchestration agent. Decomposes a request into a dependency DAG, assigns specialist agents per node, and supervises level-ordered parallel execution. | `agent_run(name: "coordinator")` |
| database | Database schema design agent. Owns migration files, ER description, query plans, and risk report. Read-only on the live DB. | `agent_run(name: "database")` |
| deploy-infra | Infrastructure provisioning agent. Owns Terraform/CloudFormation/CDK module set, IAM policies, provisioning plan. Does not apply infra. | `agent_run(name: "deploy-infra")` |
| deployinfra | AWS Infrastructure Auto-Setup Agent - Uses shared infrastructure (ALB, S3, CloudFront) | `agent_run(name: "deployinfra")` |
| deployment | Deployment agent. Reads a deployment request, emits a structured plan (build/upload/switch/smoke/verify + rollback), executes via PIL pipelines only, and emits a deployment report. | `agent_run(name: "deployment")` |
| design-analyst-quintet | Design audit Pass 2 single-axis analyst. Axis-parametrized (width-spacing/typography/color-contrast/radius-shadow/motion). 5 parallel instances under design-controller. | `agent_run(name: "design-analyst-quintet")` |
| design-claude-design-brief-exporter | DCA SSOT (DESIGN.md modular) を Claude Design 用 prompt + asset bundle に変換し、外部 export する specialist agent。 | `agent_run(name: "design-claude-design-brief-exporter")` |
| design-claude-design-importer | External-inbound Claude Design handoff bundle importer. Multi-format (HTML/PPTX/PDF/Canva/ZIP/InternalUrl) parser dispatch. Converts to intent + architecture layer proposals. | `agent_run(name: "design-claude-design-importer")` |
| design-coherence-validator | Architecture-layer Axiom 2 (Coherence) validator. Quantifies Intent->Architecture path_quality (coverage * alignment per statement). Read-only. | `agent_run(name: "design-coherence-validator")` |
| design-concept-planner | Intent-layer concept planner. Drafts design intent + differentiation pillars from researcher output. Composes concept proposal with measurable axes + alignment checks. | `agent_run(name: "design-concept-planner")` |
| design-controller | Cross-layer orchestrator for design lifecycle (intent->architecture->manifestation 3-layer pipeline). Dynamic swarm composition + DAG construction + parallel execution + self-feedback loop + DESIGN.md SSOT integrity. | `agent_run(name: "design-controller")` |
| design-figma-importer | External-inbound Figma file importer via Figma Remote MCP. Extracts metadata/frames/fills/text/Variables, converts to intent + architecture layer proposals. Never writes to Figma or SSOT. | `agent_run(name: "design-figma-importer")` |
| design-figma-token-syncer | Bidirectional consistency checker between DESIGN.md token SSOT and Figma Variables. Detects drift, classifies severity, produces PR-style change set for improver agent. | `agent_run(name: "design-figma-token-syncer")` |
| design-fix-plan | Design audit Pass 3 — 5 axis analyst findings を統合し、優先度付き fix plan + REPORT.md を生成する Manifestation layer specialist agent。community-platform 05 移植。 | `agent_run(name: "design-fix-plan")` |
| design-improver | Cross-layer improver. Reads SelfFeedback evaluation, generates PR-style change set proposing targeted SSOT module updates. Each change scoped to single module with axiom-aligned rationale + severity. | `agent_run(name: "design-improver")` |
| design-knowledge-recorder | Cross-layer knowledge recorder. Persists design lifecycle knowledge to decision/learning/postmortem/SSOT module/wiki. Append-only with sanitization + versioning + path-bounded authority. | `agent_run(name: "design-knowledge-recorder")` |
| design-philosophy-extractor | Intent-layer specialist for Reverse Structure Inference (RSI). Extracts implicit design philosophy from existing artifacts (codebase/Figma/handoff/brand docs). Output is candidate-only. | `agent_run(name: "design-philosophy-extractor")` |
| design-philosophy-researcher | Intent-layer researcher. Surveys design philosophies/patterns/theory/competitors across web + repo + reference docs. Ranks findings + proposes candidate concepts. | `agent_run(name: "design-philosophy-researcher")` |
| design-reviewer-orchestrator | Manifestation layer の 3 quality review (brand-compliance-check / frontend-design-suite quality / design-reviewer skill) を orchestrate する specialist agent。Conflict C2 解決 + C3 (Affect_i 暗黙依存) wrap 担当。 | `agent_run(name: "design-reviewer-orchestrator")` |
| design-section-architect | Architecture-layer section structure designer. Produces section taxonomy + layout grid + breakpoints + z-index scale + section anti-patterns. Downstream from concept + token architect. | `agent_run(name: "design-section-architect")` |
| design-section-detector | Design audit Pass 1.5 section detector. Classifies pages into named sections (hero/feature/cta/etc), detects width overflow + overlap + spacing inconsistency. Produces breakage report with crops. | `agent_run(name: "design-section-detector")` |
| design-self-feedback-evaluator | Cross-layer evaluator quantifying Axiom 4 (Preservation) + Axiom 5 (Completeness). Computes information_increment + reach_ratio. Drives improvement cycle. Read-only. | `agent_run(name: "design-self-feedback-evaluator")` |
| design-snapshot | Design audit Pass 0 manifestation-layer snapshot agent. Captures screens/DOM/computed CSS for target URLs. Produces structured artifact bundle for downstream auditors. | `agent_run(name: "design-snapshot")` |
| design-token-architect | Architecture-layer token architect. Designs design tokens (color/typography/spacing/shadow/radius/motion), normalizes to DESIGN.md SSOT modules + design-system.yml. Never auto-applies; PR-style change set output. | `agent_run(name: "design-token-architect")` |
| design-token-inventory | Design audit Pass 1 token inventory agent. Compares SSOT design tokens vs implementation (globals.css/Tailwind/inline). Severity-classified conflict report. | `agent_run(name: "design-token-inventory")` |
| dev-observer | CDP直接制御による開発デバッグアシスタント。 統合ログ収集(server+browser+network)、自動スクリーンショット、 CLS検出、React Component Explorer、UI要素ビジュアル指定を提供。 | `agent_run(name: "dev-observer")` |
| devops | DevOps definitions agent. Owns CI/CD pipeline files, IaC modules, deployment runbooks. Does not push infrastructure. | `agent_run(name: "devops")` |
| docker-host-admin | Container host operations specialist (gpuserver/AWS ECS host). Lifecycle + cleanup + monitoring. ProtectActiveContainers + RequireAckForMutation invariants. | `agent_run(name: "docker-host-admin")` |
| documentation | Documentation generation agent. Owns docs tree (API ref, runbook, ADR, user manual). Read-only on src; emits files + anchor graph + link audit + gaps. | `agent_run(name: "documentation")` |
| formal-abstraction | ★ Tier 0 Problem Framing agent ★. BEFORE any implementation/research, lifts the problem to formal mathematical or CS-theoretic structures. Searches problem-pattern-catalog for existing frameworks (sheaf cohomology, automata, SAT, AGM postulates, factor graphs, etc). Forces discipline rotation through 7+ disciplines. Outputs framework recommendation BEFORE Tier 1 starts. Built-in defense against \"Engineering before Theory\" failure mode. | `agent_run(name: "formal-abstraction")` |
| frontend | Frontend implementation agent. Produces UI components, view state, and tests for a specified surface, plus a build-and-verify checklist. | `agent_run(name: "frontend")` |
| hitl | Human-in-the-loop approval gate. Risk-classifies pending op, presents structured prompt, records decision + audit trail. Never executes the underlying op. | `agent_run(name: "hitl")` |
| incident | Incident coordination agent. Owns incident report, timeline, working theory, mitigations, postmortem skeleton. Does not execute mitigations or draft external comms. | `agent_run(name: "incident")` |
| infrastructure-controller | Infrastructure orchestration controller. Gates ops via 5 invariants (cleanup pre-inventory / no-active-asset / snapshot-before-destroy / post-cleanup-verify / budget-respect). Leads aws-agent + deploy-infra + docker-host-admin swarm. | `agent_run(name: "infrastructure-controller")` |
| intent-guard | Pre-tool drift detector. Runs D1/D3/D6 BLOCK + Alt-A WARN regex catalog against Edit/Write candidates. Returns exit 0/1/2 per verdict. | `agent_run(name: "intent-guard")` |
| issue | Issue classification agent. Reads one GitHub issue, emits a label set, priority, severity, agent assignment, and effort estimate. Read-only; does not edit issues. | `agent_run(name: "issue")` |
| janitor | System-wide periodic janitor (cron-only at SessionStart). Health scans .ccm/.pil-state/mailbox/journal; mutates with ack only. | `agent_run(name: "janitor")` |
| jj-branch | jj branch-strategy specialist. Owns dev-main split, hotfix path, backport, train promotion. Plan-first; respects ADR + freeze + protection. | `agent_run(name: "jj-branch")` |
| jj-janitor | jj periodic housekeeping specialist (cron-like). Owns stale-bookmark prune, keep-ref aging, lock detection. Read-only by default. | `agent_run(name: "jj-janitor")` |
| jj-ops | jj day-to-day VCS specialist. Owns describe/new/push/fetch/snapshot/bookmark via PIL when applicable. Non-destructive only. | `agent_run(name: "jj-ops")` |
| jj-snapshot | jj snapshot + recovery specialist. Owns op-log restore, keep-ref maintenance, undo. Destructive ops require explicit ack. | `agent_run(name: "jj-snapshot")` |
| lark-analytics-specialist | Lark ecosystem data analytics & BI agent. Reads Base/IM/Calendar through Lark MCP, computes deterministic aggregated metrics, emits structured analytics report routed to Lark chat/Docs/email. | `agent_run(name: "lark-analytics-specialist")` |
| lark-approval-hr | Lark approval workflow + HR operations agent. Submits/tracks approval instances, queries attendance, orchestrates onboard sequences via Lark MCP. Idempotent + audit-trail-aware. | `agent_run(name: "lark-approval-hr")` |
| lark-browser-admin | Lark admin console operator via managed browser session. Last-resort path for admin tasks not covered by public API. Captures screenshots + audit log per mutation. | `agent_run(name: "lark-browser-admin")` |
| lark-enterprise-orchestrator | Multi-step Lark business process orchestrator. Decomposes goal into task DAG across Base/IM/Docs/Calendar, delegates leaf actions to Lark specialists, emits integrated execution report. | `agent_run(name: "lark-enterprise-orchestrator")` |
| lark-integration-bridge | Lark ↔ external system integration bridge. Maps Base/IM/Calendar records to/from foreign data stores with schema-aware transforms, conflict policy, retry budget. | `agent_run(name: "lark-integration-bridge")` |
| lark-message-ops | Lark messaging operations agent. Sends/edits messages, broadcasts to groups, posts interactive cards, manages chat membership. Append-only with delivery report per recipient. | `agent_run(name: "lark-message-ops")` |
| learning-curator | Wiki knowledge graph curator. Detects new entries needing curation, deduplicates, classifies, links. Curates structure; does not author content. | `agent_run(name: "learning-curator")` |
| license-management | License verification agent. Reads license artefact, validates signature + revocation, emits verdict report. Read-only; never issues or revokes. | `agent_run(name: "license-management")` |
| licensemanagement | ライセンス管理専門Agent - LMC統合とライセンス検証システム | `agent_run(name: "licensemanagement")` |
| migration | Migration planning agent. Owns migration plan + forward/reverse scripts + verify recipe. Plan-only; DeploymentAgent owns cutover. | `agent_run(name: "migration")` |
| monitoring | Observability design agent. Owns SLI/SLO definitions, alert rules, log routing, dashboards, on-call runbook. Does not instrument code. | `agent_run(name: "monitoring")` |
| north-star | Long-term goal vector drift detector. Computes drift score per PR/Issue, escalates after 3 consecutive drifts. Advisory only; never blocks. | `agent_run(name: "north-star")` |
| omega-guard | Invariant violation detector (IC-1..IC-5) across surfaces. Meta agent at theta-gate points; advisory + recommendation. NoAutoFix. | `agent_run(name: "omega-guard")` |
| optimization-agent | Cross-cutting optimization advisor. Reads perf/refactor/debt signals, emits prioritized roadmap with ROI sort and routing to specialist agents. | `agent_run(name: "optimization-agent")` |
| optimization | パフォーマンス・コード最適化Agent - リファクタリング・品質改善・技術的負債解消 | `agent_run(name: "optimization")` |
| performance | Performance measurement agent. Owns profiling, benchmarks, load tests, bottleneck reports, optimization recommendations. Read-only on source. | `agent_run(name: "performance")` |
| pil-workflow-agent | プロジェクトコンテクストからPILワークフローを自動生成するEnterprise専用エージェント。 CCI + context-eng でプロジェクトを分析し、テンプレートを選択・カスタマイズ。 Rust承認ゲート付きで品質保証。 | `agent_run(name: "pil-workflow-agent")` |
| pipeline-controller | PIL pipeline orchestration controller. Launches / monitors / recovers from C1-C4 known patterns. Novel patterns escalate to CoordinatorAgent. | `agent_run(name: "pipeline-controller")` |
| pr | Pull request request agent. Reads a finished change set and emits a structured PR request (title, body, base/head, draft, reviewers, closes_issues). Read-only; the caller submits the PR. | `agent_run(name: "pr")` |
| qa | QA strategy agent. Owns test plan, matrix, data strategy, exit criteria, risk report. Does not write or run individual tests. | `agent_run(name: "qa")` |
| refactor | Refactor planning agent. Owns behaviour-preserving refactor plans with impact analysis, mechanical steps, rollback paths. Does not edit code. | `agent_run(name: "refactor")` |
| refresher | Project status reconciliation agent. Audits drift across GitHub Issues/PRs/CI/wiki, emits drift report. Read-only by default; never closes issues. | `agent_run(name: "refresher")` |
| release | SDKリリース統括Agent — ビルド・検証・RQT・S3アップロード・E2Eテストの全フローを自律実行 | `agent_run(name: "release")` |
| review | Code quality review agent. Reads a change set, runs the configured checks, scores the result, and emits a verdict with optional escalation. | `agent_run(name: "review")` |
| rust-migration | TypeScript-to-Rust migration planner. Emits Rust source + NAPI/wasm bindings + equivalence tests + benchmark ratio + roadmap. Keeps TS as rollback path. | `agent_run(name: "rust-migration")` |
| rustmigration | TypeScript→Rust移行専門Agent - 安全なRust移行とNAPIバインディング生成 | `agent_run(name: "rustmigration")` |
| sd-analyze | | | `agent_run(name: "sd-analyze")` |
| sd-generate | | | `agent_run(name: "sd-generate")` |
| sd-research | | | `agent_run(name: "sd-research")` |
| security-agent | Security audit agent. Owns audit document with threats, findings (CVSS), recommended controls, residual-risk note, citations. Read-only; does not patch. | `agent_run(name: "security-agent")` |
| security-learner-agent | Learns new defect detection patterns from incidents and feedback. Registers regex matchers + remediation templates to the pattern registry. | `agent_run(name: "security-learner-agent")` |
| security-planner-agent | Infers security requirements at API route design time. Generates secure boilerplate template + regression test scaffold. Read-only on source. | `agent_run(name: "security-planner-agent")` |
| security-scanner-agent | Defensive code-level security defect detector. Classifies findings by severity and defect class. Read-only. | `agent_run(name: "security-scanner-agent")` |
| security | Web service security CSO. End-to-end security audit, vulnerability scan, posture scoring, severity-routed remediation report. Read-only on source. | `agent_run(name: "security")` |
| test | Test execution agent. Runs suites described by a test plan and emits a structured report (results, coverage, flakiness, perf, artefacts). Does not modify production code. | `agent_run(name: "test")` |
| threejs | Three.js 3Dシーン構築・レンダリング・コード生成の専門Agent。 E:Stack Theory (Intent→Architecture→Manifestation) に基づく デザイン品質保証。R3F/vanilla 両対応、headlessレンダリング対応。 | `agent_run(name: "threejs")` |
| tmux-control | Tmux session control agent. Manages sessions/windows/panes, emits structured op report. Refuses destructive key sends and protected session kills. | `agent_run(name: "tmux-control")` |
| tmuxcontrol | Tmux Control Agent - tmuxセッション制御・マルチペイン管理 | `agent_run(name: "tmuxcontrol")` |
| ux-review | UX analysis agent. Walks a surface as a persona, emits structured UX report (journey, friction, a11y, Nielsen heuristics, recommendations). Read-only. | `agent_run(name: "ux-review")` |
| uxreview | ユーザー視点でUI/UXを分析し、カスタマージャーニーに基づく改善提案を行う | `agent_run(name: "uxreview")` |
| vcs-controller | VCS orchestration controller. Gates jj/git ops via 5 invariants (pre-restore / parallel-workspace / snapshot-before-destructive / op-log-trace / post-recovery-verify). Leads jj-ops + jj-branch + jj-snapshot + jj-janitor swarm. | `agent_run(name: "vcs-controller")` |
| wiring-maintenance | 4-way wiring graph (SSOT/generated/plan/issue/code) drift detector. Generates cascade-repair PR draft for HITL review. NEVER auto-merges. | `agent_run(name: "wiring-maintenance")` |
| xkoma-agent | Xkoma AI Agent MCP Server との連携エージェント。 セッション管理、メモリ、キュー、セキュリティ監査を提供。 | `agent_run(name: "xkoma-agent")` |

---
*Generated by CCAGI SDK*

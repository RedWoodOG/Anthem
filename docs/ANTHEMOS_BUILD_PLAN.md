# AnthemOS Build Plan

## 1. Purpose

AnthemOS is intended to become a commercial, user-owned AI operating system. It should feel less like an app bolted onto a conventional platform and more like a private life runtime: an environment where identity, memory, consent, local context, and companion behavior are OS-level concerns.

The goal is not to rebuild Aura/TCF under new names. Aura and TCF are source concepts for memory continuity, personal state, and cognition. AnthemOS should use those ideas as influence, then build a different operating system architecture around explicit consent, recoverable identity, device-aware context, and a practical desktop-first product path.

The first version should not attempt a full kernel replacement. Redox OS already provides a Rust microkernel, userspace services, a package/build system, and a scheme-based OS interface. AnthemOS should begin by extending that model with Anthem-owned services and policies.

## 2. Product Thesis

Most current AI assistants live inside somebody else's platform. They are present only when the host OS, app store, browser, cloud account, or phone vendor allows them to be present. AnthemOS should invert that relationship.

AnthemOS should make the personal AI runtime part of the user's own computing environment.

The pitch version is simple:

> AnthemOS is an operating system that can know you over time because you gave it permission to remember, you can see what it remembers, and you can take that memory with you.

That means the technical system must support:

- Long-term memory without uncontrolled storage growth.
- Recoverable personal state after hardware or cloud failure.
- Consent as a runtime primitive, not a settings page.
- Local-first operation when possible.
- Clear separation between OS state, AI memory, telemetry, and user-owned archives.
- A commercial path that does not depend on being accepted inside Apple, Google, or Microsoft ecosystems.

## 3. Foundation Choice

### 3.1 Why Redox First

Redox OS is a practical foundation because it is already a real Rust-based OS with:

- A microkernel architecture.
- A scheme-based interface between kernel and services.
- A base userland made of daemons and drivers.
- A build system capable of producing OS images.
- A permissive license posture suitable for commercial exploration, subject to complete license review.

The Redox kernel is compact compared with mainstream kernels, but it still owns the hardest low-level boundaries:

- Boot entry.
- Architecture-specific syscall and interrupt paths.
- Process contexts.
- Virtual memory and page grants.
- Kernel schemes.
- File descriptors.
- Syscall dispatch.
- Kernel/user isolation.

Because of that, AnthemOS v1 should not replace the kernel. A full new kernel would delay the AI-OS product for years before the core Anthem experience could be tested.

### 3.2 What Anthem Owns

Anthem should own the layer that makes the system meaningfully different:

- Consent policy.
- Personal runtime state.
- Long-term memory management.
- Device context.
- Recovery identity.
- AI runtime orchestration.
- Local/cloud boundary decisions.
- Desktop shell experience.

Redox provides the substrate. Anthem provides the human-centered OS behavior.

## 4. Architecture Overview

AnthemOS should be built as a layered Redox-derived system.

```text
Hardware
  |
Redox microkernel
  |
Redox schemes, drivers, memory, process, syscall, and base services
  |
Anthem service kernel layer
  |
Lifetime consent runtime
  |
Aura/TCF-inspired memory and cognition runtime
  |
Desktop shell, companion, applications, and device experiences
```

The critical architectural decision is that Anthem's first "new kernel" is not a rewritten microkernel. It is a service kernel layer: privileged OS services that behave like core platform infrastructure while keeping the underlying Redox kernel stable.

## 5. Anthem Service Kernel Layer

The service kernel layer is the first major implementation target. It should be made of Redox userspace schemes and daemons that register early in boot and expose Anthem-specific system services.

### 5.1 Proposed Schemes

#### anthem-consent:

Stores and enforces human permission state.

Responsibilities:

- Track what the runtime may observe.
- Track what the runtime may remember.
- Track what the runtime may infer.
- Track what the runtime may sync.
- Track what the runtime may share with apps or cloud services.
- Require human approval for privilege expansion.
- Provide an audit trail for consent changes.

Non-goal:

- It must not become a hidden policy engine that silently grants itself power.

#### anthem-memory:

Stores long-term user/runtime memory.

Responsibilities:

- Persist durable memory records.
- Preserve event chains without storing every raw interaction forever.
- Maintain summaries, state transitions, provenance, and recovery points.
- Support compaction without deleting meaningful history.
- Expose inspection and deletion tools.
- Separate personal facts from inferred traits.
- Support encrypted local storage and portable backup.

Non-goal:

- It must not become generic RAG with a branding layer.

#### anthem-identity:

Manages continuity across hardware changes.

Responsibilities:

- Bind the runtime to the human, not to one motherboard, one disk, or one vendor account.
- Support device enrollment and revocation.
- Recover from hardware failure.
- Restore local memory archives.
- Avoid Windows-style relicensing when a machine dies.
- Support offline ownership proofs where possible.

Non-goal:

- It must not create a central account dependency that can lock the user out of their own life runtime.

#### anthem-telemetry:

Handles local hardware and sensor context.

Responsibilities:

- Expose device state to the runtime only through consent.
- Normalize events from battery, location, motion, peripherals, cameras, microphones, network state, and future sensors.
- Allow per-sensor visibility and retention rules.
- Prefer edge/local processing before persistence.

Non-goal:

- It must not become always-on surveillance.

#### anthem-runtime:

Coordinates the AI companion and memory runtime.

Responsibilities:

- Manage local model services or remote model adapters.
- Use memory through consent-scoped APIs.
- Maintain session state.
- Request access rather than assume access.
- Convert raw life events into structured memory updates.
- Provide a stable runtime interface for shell and apps.

Non-goal:

- It must not be a monolithic replica of Aura/TCF.

## 6. Aura/TCF Memory Runtime

The memory system should solve the problem the user actually cares about: long-term continuity without endless raw memory growth or destructive forgetting.

Anthem memory should not merely store embeddings and call that intelligence. It should store state changes in a way that preserves how the present became true.

Example:

> "My old animal Skippy passed away, and I got a new one named Jester."

The system should not overwrite Skippy with Jester. It should store:

- Skippy existed.
- Skippy mattered.
- Skippy passed away.
- The event changed the user's life state.
- Jester later entered the user's life.
- Jester is current.
- Skippy remains historical and emotionally relevant.

This requires a memory model with timelines, state transitions, durable facts, emotional salience, and revocation rules.

### 6.1 Memory Tiers

Anthem should separate memory into tiers:

- Working memory: active session context.
- Recent memory: high-resolution short-term history.
- Durable state: long-lived facts and relationships.
- Transition memory: how one life state became another.
- Archive memory: compressed historical records with provenance.
- Revoked memory: tombstones or deletion markers proving something was removed or hidden.

### 6.2 Growth Strategy

The system should grow over time, but not linearly with raw conversation volume.

Raw interaction data should be treated as temporary unless the user explicitly chooses to retain it.

Durable storage should favor:

- Facts.
- Changes.
- Relationships.
- Preferences.
- Consent records.
- Summaries with provenance.
- Important source references.
- Emotional and practical state transitions.

Compaction must be transparent. The user should be able to ask:

- What do you remember about this?
- Why do you believe this?
- When did this become true?
- What did you forget or compress?
- Can this be deleted?
- Can this be kept forever?

### 6.3 Difference From RAG

Anthem memory is not just retrieval augmented generation.

RAG usually means:

- Store chunks.
- Embed chunks.
- Retrieve relevant chunks.
- Send them to a model.

Anthem memory should instead behave like a living private state system:

- It tracks current state.
- It tracks previous states.
- It tracks transitions.
- It records consent.
- It stores why memory exists.
- It distinguishes evidence from inference.
- It supports long-term continuity across devices.
- It can explain what changed.

Embeddings may still be used as one search tool, but they are not the memory architecture.

## 7. Lifetime Consent Runtime

The lifetime consent runtime is the hard constant of AnthemOS: the human is always in the loop.

This changes the system design in several ways:

- The runtime cannot silently expand observation.
- The runtime cannot silently retain sensitive input.
- The runtime cannot silently sync personal memory.
- The runtime cannot silently share memory with apps.
- The runtime cannot silently activate sensors.
- The runtime cannot silently infer protected or intimate traits for later use.

Consent should be contextual, durable, revocable, and inspectable.

### 7.1 Consent Records

Consent records should include:

- Who granted permission.
- What was granted.
- When it was granted.
- Which subsystem requested it.
- What data scope it covers.
- How long it lasts.
- Whether it may be synced.
- Whether it may be used for inference.
- Whether it may be shared with applications.
- How it can be revoked.

### 7.2 Human-In-The-Loop Policy

The system should support automatic behavior only inside explicit boundaries.

Examples:

- Allowed: "Remember my work schedule."
- Not allowed by default: "Analyze every file on the disk and infer my job stress."
- Allowed: "Use laptop battery and calendar state to suggest when to pause."
- Not allowed by default: "Upload sensor history to optimize cloud predictions."

The OS should make expansion visible and ask when boundaries change.

## 8. Device And Sensor Layer

AnthemOS should eventually become more than a desktop companion. On edge devices, the runtime can use hardware context to become situationally useful.

Examples:

- Battery, thermal, and performance state can shape how models run.
- Location can support reminders and safety routines when explicitly allowed.
- Motion and wearables can support health-adjacent routines without claiming medical authority.
- Cameras and microphones can support perception only through clear activation and consent.
- Network state can determine when to run locally or defer sync.
- Peripheral state can help the runtime understand work context.

The rule is simple: sensor power must be visible, scoped, and revocable.

## 9. Backup, Recovery, And Hardware Failure

AnthemOS must avoid the failure mode where the user's life runtime dies with one machine.

The identity and memory system should support:

- Encrypted local backups.
- User-owned recovery keys.
- Multiple trusted devices.
- Device revocation.
- Offline restore packages.
- Optional cloud escrow with explicit consent.
- Exportable memory archives.
- Versioned schema migration.

The user should not need to buy a new OS key because a motherboard failed. Commercial licensing, if present, should bind to the user entitlement and recovery process, not to a brittle single-device fingerprint.

## 10. Desktop-First Product Path

AnthemOS should begin on desktop-class hardware because:

- Debugging is easier.
- Storage and memory budgets are larger.
- Redox is closer to practical desktop experimentation than mobile deployment.
- The AI runtime can be prototyped without fighting phone vendor constraints.
- A desktop OS can prove the architecture before custom devices exist.

The first desktop goal is not to beat Windows, macOS, or Linux on every feature. The first goal is to prove that a consent-based AI runtime belongs at the OS layer.

## 11. Mobile And Edge Path

Mobile and edge support should come later.

The eventual path:

- Stabilize Anthem runtime APIs on desktop.
- Define portable memory archive formats.
- Define device enrollment and sync protocols.
- Create minimal edge runtime profiles.
- Build hardware abstraction for sensors.
- Create low-power local inference policies.
- Move from desktop companion to portable companion.

Anthem should not begin by depending on Apple or Google app store presence. A future custom device line, dedicated edge device, or OEM partnership can give Anthem direct platform presence.

## 12. Commercial Platform Notes

A commercial AnthemOS platform must handle:

- Redox license compliance.
- Third-party license inventory.
- Trademark separation from Redox.
- Branding and product marks.
- Security update policy.
- Recovery and entitlement policy.
- Export controls for cryptography where applicable.
- Privacy commitments that are enforceable in design, not just marketing.

Redox's permissive licensing posture makes commercial exploration plausible, but Anthem must perform a full legal and dependency review before shipping anything commercial.

## 13. Build Phases

### Phase 0: Repository Foundation

Deliverables:

- Project README.
- Detailed build plan.
- License decision.
- Contribution policy.
- Architecture decision records.
- Commercial constraints document.

Acceptance criteria:

- The repo explains what AnthemOS is.
- The repo explains why Redox is the first foundation.
- The repo states that v1 does not replace the Redox kernel.

### Phase 1: Redox Build Fork

Deliverables:

- Fork or vendor Redox build-system integration.
- Create an Anthem build profile.
- Produce a bootable Redox-derived image.
- Add branding at boot and package level.
- Track upstream Redox commit and dependency versions.

Acceptance criteria:

- A developer can build an Anthem image.
- The image boots in QEMU.
- The image includes a minimal Anthem identity marker.

### Phase 2: Anthem Init Services

Deliverables:

- Add early boot services for Anthem.
- Register first Anthem schemes.
- Add service readiness notifications.
- Add logs and diagnostic endpoints.

Acceptance criteria:

- `anthem-consent:` registers.
- `anthem-memory:` registers.
- `anthem-runtime:` registers.
- Services start in deterministic order.
- Failure is visible and recoverable.

### Phase 3: Consent Runtime Prototype

Deliverables:

- Consent record schema.
- Consent storage backend.
- Policy query API.
- Human-readable audit view.
- Revocation path.

Acceptance criteria:

- Runtime components must request permission.
- Consent changes are persisted.
- Revoked permissions block future access.
- The user can inspect what is allowed.

### Phase 4: Memory Runtime Prototype

Deliverables:

- Memory record schema.
- State transition model.
- Timeline model.
- Archive and compaction process.
- Inspection API.
- Export/import format.

Acceptance criteria:

- The Skippy/Jester scenario preserves past and current state.
- Compaction does not erase meaningful transitions.
- Memory can be exported and restored.
- The runtime can explain why a memory exists.

### Phase 5: Aura/TCF Runtime Adapter

Deliverables:

- Map Aura/TCF concepts into Anthem memory primitives.
- Keep TCF as influence, not foundation.
- Add runtime orchestration for companion behavior.
- Define model-provider adapter boundary.

Acceptance criteria:

- Anthem can use Aura-like continuity without copying the original architecture.
- Model calls are separated from memory authority.
- Local and remote model modes are both possible.

### Phase 6: Desktop Shell Integration

Deliverables:

- Desktop companion surface.
- Consent prompts.
- Memory inspection UI.
- Recovery status UI.
- Runtime activity indicator.

Acceptance criteria:

- The user can see when Anthem is active.
- The user can approve or deny access.
- The user can inspect, edit, export, and delete memory.

### Phase 7: Backup And Recovery

Deliverables:

- Encrypted memory archive.
- Device enrollment.
- Device revocation.
- Restore flow.
- Recovery key handling.

Acceptance criteria:

- A test user can migrate from one machine to another.
- Memory restores without requiring the original hardware.
- A lost device can be revoked.

### Phase 8: Edge And Mobile Adaptation

Deliverables:

- Minimal runtime profile.
- Sensor consent layer.
- Local telemetry normalization.
- Low-power model policy.
- Sync policy.

Acceptance criteria:

- Anthem can run a reduced companion profile on constrained hardware.
- Sensor data is gated by consent.
- Memory sync respects user policy.

## 14. Technical Risks

### Kernel Drift

If Anthem modifies the Redox kernel too early, it inherits a long-term maintenance burden. Avoid kernel changes until a required primitive cannot be implemented as a userspace scheme or daemon.

### Memory Bloat

If raw history is retained forever, storage grows without discipline. Use tiered memory, compaction, transition records, and user-controlled archives.

### Fake Consent

If consent becomes a buried preference screen, the product fails its core promise. Consent must be runtime-visible and enforced.

### Cloud Capture

If recovery requires one cloud provider, Anthem becomes the kind of lock-in it is trying to avoid. Cloud can be optional, but user-owned backup must exist.

### RAG Regression

If memory becomes chunk retrieval plus embeddings, Anthem loses its distinct value. Retrieval can be a tool, but memory must be structured state.

### Hardware Ambition Too Early

Building custom devices before the runtime works would increase cost and risk. Prove desktop first.

## 15. Hard Boundaries

AnthemOS should not:

- Secretly activate sensors.
- Silently upload private memory.
- Bind recovery to one hardware fingerprint.
- Treat consent as a one-time blanket waiver.
- Replace the Redox kernel in v1.
- Present RAG as solved long-term memory.
- Delete meaningful past state just because current state changed.
- Hide AI memory from the user.

## 16. First Engineering Milestone

The first real engineering milestone after this documentation phase should be:

> Boot a Redox-derived Anthem image that registers `anthem-consent:`, `anthem-memory:`, and `anthem-runtime:` as early services, then stores and retrieves a consent-scoped memory transition through a local test UI or command-line tool.

This proves the foundation without pretending the whole OS exists yet.

## 17. Practical Depth Estimate

Rough estimates depend on team size and available time, but the depth is approximately:

- Documentation and repo foundation: days.
- Bootable Redox-derived Anthem profile: weeks to months.
- First Anthem schemes and services: months.
- Working consent and memory prototype: months.
- Product-quality desktop runtime: 1 to 2+ years.
- Full independent kernel replacement: multi-year research OS effort.

The practical product path is to build the Anthem service kernel layer first, then only move deeper into the kernel if the runtime proves it needs a primitive Redox cannot safely provide.

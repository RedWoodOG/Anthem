# AnthemOS

AnthemOS is a desktop-first AI operating system concept built around a lifetime consent runtime, private local memory, and a portable companion layer that can move across devices without turning the user into a cloud account or a hardware license hostage.

The first technical foundation is Redox OS: a Rust-based microkernel operating system with a userspace service model that is well suited for building Anthem as a new OS personality without starting from a blank kernel. Aura/TCF informs the long-term memory and cognition model, but AnthemOS is not intended to rebuild Aura directly. The goal is a separate platform that reaches the same human-centered endpoint through a cleaner operating-system foundation.

## Core Idea

AnthemOS treats the human as the permanent authority in the system.

- The OS should remember through consent, not surveillance.
- The AI runtime should be portable across hardware failure, upgrades, and device changes.
- Long-term memory should be structured, inspectable, revocable, and recoverable.
- Device telemetry should serve the user, not become a hidden data extraction layer.
- Desktop comes first, with mobile and edge devices following after the runtime is proven.

## Build Plan

The full build plan is in [docs/ANTHEMOS_BUILD_PLAN.md](docs/ANTHEMOS_BUILD_PLAN.md).

That plan covers:

- Redox OS as the first foundation.
- The Anthem service kernel layer.
- Aura/TCF-inspired memory runtime design.
- Lifetime consent and recovery systems.
- Desktop-first implementation phases.
- Later mobile, edge, and hardware product paths.
- Commercial platform constraints and licensing concerns.

## Current Status

This repository currently contains the planning foundation for AnthemOS. Source code, Redox integration, runtime prototypes, and build automation should be added in later phases after the architecture is locked.

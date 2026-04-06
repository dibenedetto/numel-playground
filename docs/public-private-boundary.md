# Numel Public vs Private Boundary

This document defines the recommended commercial split between the public Numel
repo and the private production backend.

For a more concrete feature-by-feature recommendation, see
[feature-tier-matrix.md](/c:/devel/numel-playground/docs/feature-tier-matrix.md).
That document also contains the current `safe-to-commit public surface` list to
use before publishing new admin/ops work from the public repo.

The goal is:

- keep the public repo as a real, fully working product
- keep the private backend focused on production guarantees and commercial hardening
- keep switching between `local` and `prod` seamless at the Numel interface level

## Guiding Rule

Keep **product concepts public** and keep **production guarantees private**.

That means the public repo should still contain real implementations of:

- users
- auth
- profiles
- quotas
- friendships
- spaces
- Git-backed versioning
- credentials
- runtime execution

Those things should not disappear from the public repo just because the private
backend exists. If they move entirely into the private slice, the public repo
stops being a real local/reference product and becomes only a demo shell.

## Recommended Split

### Public Repo

The public repo should keep:

- the platform domain model
- the shared HTTP contract
- the local/reference backend in `app/platform_local/`
- the backend loader and config-selected switching model
- the app/frontend/product surface
- the local database + Git + local runtime implementation
- the local auth/user/quota/friend/space/secrets flow
- the local admin bootstrap flow
- the shared deploy/docs/handoff material needed to understand the architecture

In other words, the public repo should still let someone:

- clone Numel
- run it locally
- create an admin user
- create spaces
- save and run workflows
- use credentials
- use the console and planner
- understand the platform model

### Private `app/platform_prod` Submodule

The private production slice should own:

- Django identity and related production auth deployment
- PostgreSQL-backed production metadata deployment
- Docker-isolated production runtime behavior
- production secrets backend choices and hardening
- stronger container isolation policy
- enterprise or production-only admin/ops behavior
- production observability, deployment, and operational tooling
- any proprietary or commercially sensitive hardening logic

This is where Numel becomes production-grade, not where Numel becomes
understandable.

## What Must Stay Compatible

The public and private slices must preserve the same app-facing behavior.

That compatibility requirement applies to:

- `/platform/*`
- `/spaces/*`
- `/workflow/*`
- `/executions/*`
- auth/user/profile/quota semantics
- space ownership and visibility semantics
- credentials/secrets semantics at the app layer
- current-space and current-workflow UX
- console and planner behavior

The user should be able to switch the backend by config and keep the same Numel
product surface.

## Boundary Table

| Area | Public repo | Private prod slice |
| --- | --- | --- |
| Domain model | Yes | Must implement it, not redefine it |
| HTTP/API contract | Yes | Must remain compatible |
| Local auth/users/profiles/quotas | Yes | No |
| Django identity deployment | No | Yes |
| SQLite reference metadata | Yes | No |
| PostgreSQL production deployment | No | Yes |
| Git-backed spaces/versioning | Yes | May reuse/extend |
| Local secrets backend | Yes | No |
| Production secrets hardening | No | Yes |
| Local runtime execution | Yes | No |
| Docker-isolated runtime | No | Yes |
| Frontend/app behavior | Yes | Must stay compatible |
| Local docs and handoff files | Yes | Should align with them |
| Proprietary ops/deploy hardening | No | Yes |

## What Should Not Move Entirely To Private

These areas should remain implemented in the public repo, even if the private
backend has stronger versions:

- auth
- user model
- quota model
- friendship model
- space model
- Git-backed versioning
- credential handling
- runtime execution

The private backend can replace the concrete implementation, but it should not
erase these concepts from the public product.

## Why This Is The Better Commercial Shape

This split supports both adoption and monetization:

- the public repo remains genuinely useful
- the architecture stays coherent between local and prod
- the private backend retains the hardening value
- evaluation, onboarding, and community contributions stay much easier
- the commercial value lives in production guarantees, not in hiding the basic product

## Decision Rule For Future Work

When deciding where a new feature belongs, use this check:

- if it defines or demonstrates the Numel product model, it should usually stay public
- if it provides production guarantees, enterprise hardening, or sensitive deployment logic, it can live in the private prod slice
- if removing it from public would make local Numel stop feeling like a real product, keep it public

## Current Recommendation

Keep the repo structure as:

- public repo with `platform_local`
- private `app/platform_prod` submodule for the production-ready solution

Do not strip auth, user, quota, Git, DB, Docker, or runtime concepts out of the
public/local slice. Keep the **concepts and local/reference implementations**
public, and keep the **production-grade implementations and guarantees**
private.

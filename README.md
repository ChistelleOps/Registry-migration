# Registry-migration

# Playbook: Automated Registry Migration (Google Artifact Registry to Cloudsmith)

## 📋 Executive Summary
This playbook details the architecture, strategy, and execution steps used to migrate our organization's container image registry from **Google Artifact Registry (GAR)** to **Cloudsmith**. 

To eliminate manual overhead, local storage constraints, and human error, we built a fully programmatic migration engine. This engine automatically provisions target repositories, moves assets over network memory pipes, and updates downstream application codebases by issuing automated GitHub Pull Requests.

---

## 🏗️ Architecture & Core Strategy

The migration framework splits operations into two cleanly decoupled automated phases:


### Phase 1: Registry-to-Registry Streaming
Instead of using a traditional `docker pull -> docker tag -> docker push` loop (which demands immense local disk storage and network bandwidth), the migration engine utilizes Google's **`gcrane`** tool. 
* Images stream directly over HTTPS from Google's infrastructure to Cloudsmith's edge endpoints.
* Layers already recognized by Cloudsmith (e.g., standard base Alpine, Ubuntu, or Debian layers) are skipped automatically via cross-repository blob mounting, saving hours of upload time.

### Phase 2: Git Ecosystem Automated Refactoring
A master Python orchestrator loops through our GitHub Organization using the GitHub REST API:
1. Clones every active, unarchived repository into an isolated temporary workspace.
2. Performs low-level string refactoring via targeted regular expressions (`re`) across `Dockerfiles`, Kubernetes specs (`.yaml`), Terraform files, and scripts.
3. Rewrites GitHub Actions workflows (`.github/workflows/*`) to strip Google IAM auth (`google-github-actions/auth`) and inject standardized Cloudsmith Open Container Initiative (OCI) registry logins.
4. Safely pushes modifications upstream to a dedicated migration branch.

---

## 🛠️ Technical Challenges & Resolutions Matrix

| Technical Challenge | Operational Risk | Our Solution / Resolution |
| :--- | :--- | :--- |
| **Local Disk/Bandwidth Saturation** | Local runner crashes, high network data egress charges, execution bottlenecks. | **In-memory Stream Processing:** Leveraged `gcrane cp -r` to pass image data directly between registries using network pipes without saving physical layers to disk. |
| **Manual Configuration Drift** | Typos in repository names, missing namespaces, mismatched access rules. | **Just-In-Time API Provisioning:** Integrated Cloudsmith's `/v1/repos/` endpoint directly into the loop to instantly auto-create private OCI targets matching Google's names. |
| **Broken Downstream Deployments** | CI/CD pipelines attempt to pull from Cloudsmith using dead Google cloud credentials. | **Automated Workflow Refactoring:** The engine identifies registry logins in workflows and replaces them with a secure `docker/login-action` tied to an Org-wide secret. |
| **Production Branch Corruption** | Automated scripts pushing broken or unverified configs straight to production branches. | **Isolated Branching Strategy:** All refactored code is safely routed to `feature/registry-migration-cloudsmith` branches to be vetted through peer-reviewed Pull Requests. |

---

## 🚀 Execution & Verification Guide

### Pre-requisites
Before kicking off an execution block, ensure the environment has the following tools globally available:
* Python 3.10+ (with packages: `GitPython`, `requests`, `google-auth`)
* `gcrane` CLI binary authenticated via environment variables
* A GitHub Personal Access Token (PAT) with full `repo` scopes
* A Cloudsmith API Key loaded securely

### How to Run the Sync Loop
1. Execute the Phase 1 script to automatically map and populate your new Cloudsmith organization repositories.
2. Execute the Phase 2 script to deploy refactored code branches across your GitHub organization.

### Verification Checklist for Engineering Teams
When reviewing an automated migration Pull Request, engineers should verify:
1. **Image References:** Check that all occurrences of `us-central1-docker.pkg.dev/your-project/...` have changed to `docker-registry.cloudsmith.io/your-org/...`.
2. **Pipeline Secret Visibility:** Ensure your GitHub Actions repository settings inherit the organization-wide `CLOUDSMITH_API_KEY` secret.
3. **Local Machine Pulls:** Update any local development environments or `.env` files to point to the new Cloudsmith endpoint.


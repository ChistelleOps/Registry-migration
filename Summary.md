# Engineering Deep-Dive: Migration Script Architecture & Execution Guide

This document details the precise operational requirements, technical execution logic, and step-by-step instructions for running the automated Google Artifact Registry to Cloudsmith migration project.

---

## 🏗️ 1. Phase 1: Registry Image Copier Script (`registry_sync.py`)

### What It Does & Why
This script automates the discovery, target-provisioning, and copying of images. Instead of hardcoding names or manually clicking through UIs, it connects dynamically to both registry providers to sync everything.

### Core Prerequisites & System Requirements
*   **Python Dependencies:** `google-auth`, `requests`
*   **CLI Dependencies:** `gcrane` (Must be installed on the runner's `$PATH`)
*   **Permissions Needed:**
    *   **Google Cloud:** IAM permissions to view Artifact Registry (`roles/artifactregistry.reader`).
    *   **Cloudsmith:** API token with Write/Admin access to create repositories and push packages.

### Step-by-Step Technical Execution Logic
1.  **Authentication Handshake:** The script requests a short-lived OAuth2 token from Google Cloud via the native `google.auth` library. It then feeds this token and the Cloudsmith API Key directly into `gcrane auth login` sessions behind the scenes.
2.  **Dynamic Discovery:** It runs `gcrane ls` against your root Google Artifact Registry path to map out every single image currently hosted by your team.
3.  **Just-In-Time Provisioning:** For every discovered image path, it queries the Cloudsmith REST API. If a matching target private OCI repository doesn't exist, it instantly creates it.
4.  **In-Memory Mirroring:** It triggers `gcrane cp -r` from the source path to the destination path. The image data streams straight through the execution environment's network memory pipes, preserving all image tags without downloading any files to local storage.

---

## 🛠️ 2. Phase 2: Git Code Ecosystem Refactorer Script (`code_refactor.py`)

### What It Does & Why
Once images are securely sitting in Cloudsmith, our application configurations must be pointed to the new endpoints. This script eliminates manual search-and-replace tasks across the entire development organization by automating codebase refactoring.

### Core Prerequisites & System Requirements
*   **Python Dependencies:** `GitPython`, `requests`
*   **Token Access:** A GitHub Personal Access Token (PAT) with `repo` and `read:org` scopes.
*   **GitHub Secret Setup:** You must add an Organization-level secret named `CLOUDSMITH_API_KEY` inside your GitHub settings before pipelines run.

### Step-by-Step Technical Execution Logic
1.  **Org-Wide Inventory:** The script connects to the GitHub API and dynamically lists all unarchived repositories belonging to your GitHub Organization.
2.  **Clean-Room Virtual Clone:** It loops through the list, clones each repository locally into a isolated temporary workspace directory, and checks out a brand-new branch named `feature/registry-migration-cloudsmith`.
3.  **Recursive AST/Text Search:** It scans the filesystem specifically filtering for Dockerfiles, Kubernetes manifests (`.yaml`/`.yml`), Terraform files, shell scripts, and JSON targets.
4.  **Regex Matching & String Interpolation:** It targets the specific structural footprint of the old registry (`region-docker.pkg.dev/...`) and safely reformats it into the Cloudsmith layout.
5.  **CI/CD Workflow Upgrades:** It searches `.github/workflows/` files. If Google Authentication tasks are discovered, it removes them or alters standard `docker/login-action` blocks to pass your organization's Cloudsmith parameters alongside your encrypted `${{ secrets.CLOUDSMITH_API_KEY }}` variable.
6.  **Upstream Commit & Clean Push:** If alterations are detected, it stages all modified files, runs a structured commit message, pushes the feature branch back to your GitHub remote, and purges the temporary local workspace folder.

---

## 🏃 3. Step-by-Step Order of Operations

To execute this migration successfully from start to finish without breaking active builds, follow this sequence:

### Step 1: Pre-Flight Environment Setup
Ensure your local or runner machine is configured with authenticated access to your cloud layers:
```bash
# Verify Google Cloud active credentials
gcloud auth application-default login

# Export your GitHub PAT and Cloudsmith Key to your temporary session environment
export GITHUB_TOKEN="ghp_your_token_here"
export CLOUDSMITH_API_KEY="sk_your_key_here"
```

### Step 2: Run Phase 1 (Image Transfer)
Execute the registry copier script. Ensure you monitor the logs to verify that `gcrane` completes its layer copying loops successfully.
```bash
python registry_sync.py
```
*Validation:* Log into your Cloudsmith Web UI and verify that all target repositories are now populated with your exact version tags.

### Step 3: Run Phase 2 (Code Refactoring)
Execute the codebase refactorer script. This will crawl your GitHub account and spin up individual migration tracking branches.
```bash
python code_refactor.py
```
*Validation:* Check your GitHub repositories to ensure the `feature/registry-migration-cloudsmith` branch has been successfully pushed.

### Step 4: Review and Merge Pull Requests
Have your engineering teams review the auto-generated branches via Pull Requests. Run a test CI execution on the branch to verify that code compiles, pulls seamlessly from Cloudsmith, and successfully runs your integration suites before merging to `main`.

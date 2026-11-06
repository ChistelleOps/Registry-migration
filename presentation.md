# Presentation Slide Deck: Automated Registry Migration
**Google Artifact Registry to Cloudsmith**

---

## Slide 1: Executive Summary

*   **The Mission:** Automated a complete container registry migration from Google Artifact Registry (GAR) to Cloudsmith.
*   **The Goal:** Eliminate manual migration overhead, prevent human configuration error, and ensure **zero downtime** for active development pipelines.
*   **The Tooling:** Built two specialized, automated Python orchestrators leveraging the `gcrane` engine and provider REST APIs.
*   **Governance:** Stored permanently in our centralized internal `devops-scripts` GitHub repository for a clean audit trail and long-term reusability.

---

## Slide 2: Phase 1 – Multi-Cloud Authentication Mechanics

*   **The Challenge:** Securely logging into two competing cloud provider backends simultaneously within the same script runner.
*   **The Solution:** Global, in-memory credential injection via **`gcrane auth login`** before moving any image data.
*   **Google Cloud (Source Auth):** 
    *   The script uses native Google SDKs to fetch a short-lived OAuth2 access token from our IAM environment.
    *   It pipes this token to `gcrane` using the special GCP login string `oauth2accesstoken`.
*   **Cloudsmith (Destination Auth):** 
    *   The script consumes our secure Cloudsmith API Key.
    *   It registers the session under our corporate Cloudsmith Organization namespace.

---

## Slide 3: Phase 1 – Dynamic Discovery & The Copy Loop

*   **The Challenge:** Manually tracking and creating targets for hundreds of unpredictable images and tag versions is prone to human error.
*   **The Solution:** **Zero hardcoding.** The script maps infrastructure requirements dynamically.
*   **Dynamic Discovery:** The script queries the source registry path using `gcrane ls` to automatically build a live catalog of all hosted image namespaces (e.g., `my-app`, `auth-service`).
*   **Just-in-Time Provisioning:** Cloudsmith rejects image pushes if the target repository doesn't exist yet. The Python script solves this by explicitly calling the Cloudsmith REST API to **create private repositories on the fly** ahead of the sync.
*   **Stream Processing:** It fires `gcrane cp -r <source_url> <calculated_cloudsmith_url>`. Data streams directly registry-to-registry in memory—**meaning zero local disk space is wasted downloading heavy image layers.**

---

## Slide 4: Phase 2 – Validation & Git Refactoring

*   **The Circuit Breaker (Validation):** We pause to review the Cloudsmith Web UI, confirming that calculated repositories and historic tags (`v1.0.0`, `latest`) copied flawlessly.
*   **Codebase Sync (The Second Script):** Once data is validated, we launch our codebase refactoring tool to update downstream configurations.
*   **Org-Wide Scanning:** The script uses the GitHub REST API to loop through our entire GitHub Organization, cloning active repositories into a clean virtual workspace.
*   **Configuration Sub-and-Replace:** It walks the filesystem to locate `Dockerfiles`, Kubernetes `.yaml` manifests, and Terraform blocks, updating old Google strings to our new Cloudsmith format.
*   **Pipeline Re-wiring:** It removes old Google-specific workflow tasks inside `.github/workflows/` and substitutes a standard `docker/login-action` tied to an organization-wide `CLOUDSMITH_API_KEY` GitHub secret.
*   **Safe Pull Requests:** Commits are pushed to an isolated `feature/registry-migration-cloudsmith` branch so team leads can safely review changes.

---

## Slide 5: Key Takeaways & Project Value Add

*   **Dynamic over Static:** We don't maintain static spreadsheets of image versions. The framework adapts to the active state of our cloud environment in real time.
*   **Extreme Infrastructure Efficiency:** By entirely avoiding traditional `docker pull / docker push` commands, we saved hundreds of gigabytes of disk bloat and avoided heavy network data egress costs.
*   **Clean Architectural Boundaries:** Because these are one-time-use migration scripts, they live inside our centralized **shared DevOps script library** instead of cluttering up application source code.

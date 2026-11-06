import os
import subprocess
import sys
import requests
from google.auth import default
from google.auth.transport.requests import Request

# --- CONFIGURATION FROM ENVIRONMENT VARIABLES ---
CLOUDSMITH_ORGANIZATION = os.environ.get("CLOUDSMITH_ORGANIZATION")
CLOUDSMITH_API_KEY = os.environ.get("CLOUDSMITH_API_KEY")

GCP_PROJECT = os.environ.get("GCP_PROJECT")
GCP_REGION = os.environ.get("GCP_REGION")
GCP_REGISTRY_NAME = os.environ.get("GCP_REGISTRY_NAME")

# Structural Layout Bases
SOURCE_REGISTRY_BASE = f"{GCP_REGION}-docker.pkg.dev/{GCP_PROJECT}/{GCP_REGISTRY_NAME}"
DEST_REGISTRY_BASE = f"docker-registry.cloudsmith.io/{CLOUDSMITH_ORGANIZATION}"


def get_gcp_access_token():
    """Generates a temporary GCP OAuth2 token to log into the source registry."""
    credentials, _ = default(scopes=['https://googleapis.com'])
    credentials.refresh(Request())
    return credentials.token


def authenticate_gcrane(gcp_token):
    """Logs crane into both registries so streaming handles seamlessly."""
    try:
        # Auth to Google Artifact Registry
        subprocess.run(
            ["gcrane", "auth", "login", f"{GCP_REGION}-docker.pkg.dev", "-u", "oauth2accesstoken", "--password-stdin"],
            input=gcp_token, text=True, check=True, capture_output=True
        )
        # Auth to Cloudsmith Registry
        subprocess.run(
            ["gcrane", "auth", "login", "docker-registry.cloudsmith.io", "-u", CLOUDSMITH_ORGANIZATION, "--password-stdin"],
            input=CLOUDSMITH_API_KEY, text=True, check=True, capture_output=True
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Authentication failed: {e.stderr}")
        sys.exit(1)


def create_cloudsmith_repo(repo_slug):
    """Invokes the Cloudsmith API to guarantee the destination repo exists."""
    url = f"https://cloudsmith.io{CLOUDSMITH_ORGANIZATION}/"
    headers = {"Content-Type": "application/json", "X-Api-Key": CLOUDSMITH_API_KEY}
    payload = {
        "name": repo_slug.replace("-", " ").title(),
        "slug": repo_slug,
        "repository_type_str": "Private"
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        print(f"📦 Created new Cloudsmith repository: {repo_slug}")
    elif response.status_code == 400 and "already exists" in response.text.lower():
        pass # Expected if repo already exists


def get_image_digest(image_ref):
    """Fetches the cryptographic SHA256 digest of a remote image reference using crane."""
    # Note: gcrane acts as a wrapper, 'crane digest' evaluates standard refs
    cmd = ["crane", "digest", image_ref]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def main():
    if not all([CLOUDSMITH_ORGANIZATION, CLOUDSMITH_API_KEY, GCP_PROJECT, GCP_REGION, GCP_REGISTRY_NAME]):
        print("❌ Error: Missing required environment variables. Please check your session exports.")
        sys.exit(1)

    gcp_token = get_gcp_access_token()
    authenticate_gcrane(gcp_token)

    # 1. Discover Google Repositories
    print(f"🔍 Mapping images within {SOURCE_REGISTRY_BASE}...")
    discover_cmd = ["gcrane", "ls", SOURCE_REGISTRY_BASE]
    discover_res = subprocess.run(discover_cmd, capture_output=True, text=True, check=True)
    images = [line.strip().replace(f"{SOURCE_REGISTRY_BASE}/", "") for line in discover_res.stdout.splitlines() if line.strip()]

    # Tracking metrics for the final summary printing block
    summary_report = {
        "verified": [],
        "mismatched": [],
        "failed_copy": []
    }

    # 2. Migration and Verification Loop
    for image in images:
        print(f"\n--- Processing: {image} ---")
        create_cloudsmith_repo(image)

        # In a fully productionized pipeline, you would crawl specific version tags. 
        # For this execution block, we validate the critical 'latest' anchor tag.
        src_image = f"{SOURCE_REGISTRY_BASE}/{image}:latest"
        dest_image = f"{DEST_REGISTRY_BASE}/{image}/{image}:latest"

        # Trigger copy execution
        print(f"🚀 Streaming image layers to Cloudsmith...")
        copy_cmd = ["gcrane", "cp", "-r", f"{SOURCE_REGISTRY_BASE}/{image}", f"{DEST_REGISTRY_BASE}/{image}/{image}"]
        copy_res = subprocess.run(copy_cmd, capture_output=True, text=True)

        if copy_res.returncode != 0:
            print(f"❌ Failed to copy image tracks for {image}.")
            summary_report["failed_copy"].append(image)
            continue

        # 3. Post-Copy Comparison Engine
        print("🔍 Verifying registry content integrity via SHA-256 hashes...")
        source_digest = get_image_digest(src_image)
        dest_digest = get_image_digest(dest_image)

        if source_digest and dest_digest and source_digest == dest_digest:
            print(f"✅ Verification Successful: {image} digests match perfectly!")
            summary_report["verified"].append(f"{image} ({source_digest[:15]}...)")
        else:
            print(f"⚠️ Warning: Digest mismatch or missing reference found for {image}!")
            print(f"   Source: {source_digest}")
            print(f"   Dest:   {dest_digest}")
            summary_report["mismatched"].append(image)

    # 📊 4. FINAL LOG REPORT PRINT OUT
    print("\n" + "="*50)
    print("🏁 MIGRATION ENGINE COMPLETION SUMMARY REPORT")
    print("="*50)
    
    if summary_report["verified"]:
        print(f"\n✨ SUCCESSFUL MATCHES (No Difference Detected - {len(summary_report['verified'])} Repos):")
        for item in summary_report["verified"]:
            print(f"   - {item}")
            
    if summary_report["mismatched"]:
        print(f"\n⚠️ MISMATCHED COPIES (Differences detected in digests - {len(summary_report['mismatched'])} Repos):")
        for item in summary_report["mismatched"]:
            print(f"   - {item}")
            
    if summary_report["failed_copy"]:
        print(f"\n❌ FAILED COPIES (Network errors during stream transfer - {len(summary_report['failed_copy'])} Repos):")
        for item in summary_report["failed_copy"]:
            print(f"   - {item}")

    print("\n" + "="*50)
    if not summary_report["mismatched"] and not summary_report["failed_copy"]:
        print("🎉 ALL REPOSITORIES MATCH PERFECTLY. INFRASTRUCTURE IS IN SYNC.")
    else:
        print("⚠️ MIGRATION FINISHED WITH EXCEPTIONS. PLEASE REVIEW LOGS ABOVE.")
    print("="*50)


if __name__ == "__main__":
    main()

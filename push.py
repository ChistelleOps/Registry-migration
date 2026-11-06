import os
import re
import shutil
import sys
import requests
from git import Repo

# --- LOAD CONFIGURATION FROM THE TERMINAL ENVIRONMENT ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
CLOUDSMITH_ORGANIZATION = os.environ.get("CLOUDSMITH_ORGANIZATION")

GCP_PROJECT = os.environ.get("GCP_PROJECT")
GCP_REGION = os.environ.get("GCP_REGION")
GCP_REGISTRY_NAME = os.environ.get("GCP_REGISTRY_NAME")

# The GitHub secret name that your teams use/will use to log into Cloudsmith
CLOUDSMITH_SECRET_NAME = "CLOUDSMITH_API_KEY"

# Build the exact Regular Expression to locate the old Google paths in code files
# Matches: region-docker.pkg.dev/project/gar-repo/image_name
OLD_REGISTRY_PATTERN = rf"{GCP_REGION}-docker.pkg.dev/{GCP_PROJECT}/{GCP_REGISTRY_NAME}/([a-zA-Z0-9\-_./]+)"

# Local execution scratch space folder
LOCAL_WORKSPACE = "./tmp_refactor_workspace"


def get_org_repositories():
    """Queries the GitHub API to dynamically find all active repositories."""
    print(f"📡 Querying GitHub API for repositories...")
    
    # We use a trick to automatically get the user/org profile name tied to your token
    user_res = requests.get("https://github.com", headers={"Authorization": f"token {GITHUB_TOKEN}"})
    if user_res.status_code != 200:
        print(f"❌ GitHub Auth failed. Check GITHUB_TOKEN. Response: {user_res.text}")
        sys.exit(1)
    
    owner_name = user_res.json()["login"]
    
    # Fetch repositories
    url = f"https://://github.comrepos?per_page=100&type=owner"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    repos = []
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        repos.extend([r["name"] for r in response.json() if not r["archived"]])
    else:
        print(f"❌ Failed to fetch repositories: {response.text}")
        sys.exit(1)
        
    print(f"📋 Found {len(repos)} active repositories to scan.")
    return owner_name, repos


def refactor_file_contents(file_path, is_workflow=False):
    """Parses a file to replace registry paths and fix GitHub Actions workflow logins."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    modified = False

    # 1. Update old registry string targets to Cloudsmith flat syntax
    if re.search(OLD_REGISTRY_PATTERN, content):
        def replace_match(match):
            image_name = match.group(1)
            # Result mapping: docker-registry.cloudsmith.io/org/image_name/image_name
            return f"docker-registry.cloudsmith.io/{CLOUDSMITH_ORGANIZATION}/{image_name}/{image_name}"
        
        content = re.sub(OLD_REGISTRY_PATTERN, replace_match, content)
        modified = True

    # 2. Fix GitHub Actions authentication steps from Google to Cloudsmith
    if is_workflow and modified:
        if "google-github-actions" in content or "docker.pkg.dev" in content:
            # Safely re-key docker/login-action configurations to target Cloudsmith parameters
            content = re.sub(r"registry:\s+.*docker\.pkg\.dev", "registry: docker-registry.cloudsmith.io", content)
            content = re.sub(r"username:\s+.*", f"username: {CLOUDSMITH_ORGANIZATION}", content)
            content = re.sub(r"password:\s+.*", f"password: ${{{{ secrets.{CLOUDSMITH_SECRET_NAME} }}}}" , content)

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"   ✏️ Refactored image references in: {os.path.basename(file_path)}")
        
    return modified


def process_repository(owner, repo_name):
    """Clones, refactors, and pushes an automated migration tracking branch to GitHub."""
    repo_dir = os.path.join(LOCAL_WORKSPACE, repo_name)
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)

    # Clone via authenticated remote URL URL string format
    remote_url = f"https://x-access-token:{GITHUB_TOKEN}@://github.com{owner}/{repo_name}.git"
    
    try:
        repo = Repo.clone_from(remote_url, repo_dir)
    except Exception as e:
        print(f"⚠️ Skipping {repo_name} (Could not clone or private access restricted)")
        return

    # Check out an isolated feature tracking branch 
    migration_branch = "feature/registry-migration-cloudsmith"
    new_branch = repo.create_head(migration_branch)
    new_branch.checkout()

    was_modified = False
    valid_extensions = (".yaml", ".yml", ".json", "Dockerfile", ".tf", ".sh")

    for root, _, files in os.walk(repo_dir):
        if ".git" in root:
            continue
        
        is_workflow_dir = ".github/workflows" in root

        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith(valid_extensions) or file == "Dockerfile":
                try:
                    if refactor_file_contents(file_path, is_workflow=is_workflow_dir):
                        was_modified = True
                except Exception as e:
                    pass # Skip unreadable binary/corrupted configurations safely

    # Commit and push branch back to GitHub only if strings were actually modified
    if was_modified:
        print(f"💾 Staging and committing changes for {repo_name}...")
        repo.git.add(A=True)
        repo.index.commit("chore: update container registry references from Google AR to Cloudsmith")
        
        origin = repo.remote(name="origin")
        origin.push(migration_branch)
        print(f"🚀 Pushed branch '{migration_branch}' upstream successfully!")
    else:
        print(f"✨ No old references found. {repo_name} codebase is clean.")

    # Always wipe out local temporary tracking directories to keep disk clean
    shutil.rmtree(repo_dir)


def main():
    # Basic environment configuration verification safety catch
    if not all([GITHUB_TOKEN, CLOUDSMITH_ORGANIZATION, GCP_PROJECT, GCP_REGION, GCP_REGISTRY_NAME]):
        print("❌ Error: Missing environment variables. Please check your session export flags.")
        sys.exit(1)

    if os.path.exists(LOCAL_WORKSPACE):
        shutil.rmtree(LOCAL_WORKSPACE)
    os.makedirs(LOCAL_WORKSPACE)

    owner, repositories = get_org_repositories()
    
    for repo in repositories:
        print(f"\nScanning Repository: {repo}")
        print("-" * 40)
        process_repository(owner, repo)

    shutil.rmtree(LOCAL_WORKSPACE)
    print("\n🏁 Ecosystem sync cycle complete. Review branches inside GitHub UI.")


if __name__ == "__main__":
    main()

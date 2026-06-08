"""
Infisical Secret Loader for HeadlineBot
========================================
Centralized secret management via Infisical Cloud.
Replaces per-platform secret storage (Kaggle/Colab native secrets).

User only needs to store 2 secrets in Kaggle/Colab:
  - INFISICAL_CLIENT_ID
  - INFISICAL_CLIENT_SECRET

And set 2 environment variables:
  - INFISICAL_PROJECT_ID
  - INFISICAL_ENV (default: "dev")
"""

import os
import subprocess
import sys


def detect_platform():
    """Detect runtime: Kaggle, Colab, or Local."""
    try:
        from kaggle_secrets import UserSecretsClient
        return "kaggle"
    except ImportError:
        pass
    try:
        from google.colab import userdata
        return "colab"
    except ImportError:
        pass
    return "local"


def _install_sdk():
    """Install infisicalsdk if not already available."""
    try:
        from infisical_sdk import InfisicalSDKClient
        return True
    except ImportError:
        print("📦 Installing infisicalsdk...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "infisicalsdk", "-q"],
            check=True,
        )
        return True


def get_infisical_credentials(platform=None):
    """
    Retrieve INFISICAL_CLIENT_ID and INFISICAL_CLIENT_SECRET
    from platform-native secret stores.
    """
    if platform is None:
        platform = detect_platform()

    if platform == "kaggle":
        from kaggle_secrets import UserSecretsClient
        client = UserSecretsClient()
        client_id = client.get_secret("INFISICAL_CLIENT_ID")
        client_secret = client.get_secret("INFISICAL_CLIENT_SECRET")
        return client_id, client_secret

    elif platform == "colab":
        from google.colab import userdata
        client_id = userdata.get("INFISICAL_CLIENT_ID")
        client_secret = userdata.get("INFISICAL_CLIENT_SECRET")
        return client_id, client_secret

    else:
        # Local: read from environment variables
        client_id = os.environ.get("INFISICAL_CLIENT_ID")
        client_secret = os.environ.get("INFISICAL_CLIENT_SECRET")
        return client_id, client_secret


def load_infisical_secrets(
    project_id: str,
    environment: str = "dev",
    secret_path: str = "/",
    set_env_vars: bool = True,
    platform: str | None = None,
) -> dict:
    """
    Load secrets from Infisical Cloud and inject into os.environ.

    Uses Eager Loading strategy: fetch all secrets once at startup,
    store in os.environ. No further network calls needed.

    Args:
        project_id:   Infisical Project ID (from dashboard URL)
        environment:  Environment slug ('dev', 'staging', 'prod')
        secret_path:  Folder path in Infisical (default: root '/')
        set_env_vars: If True, auto-set secrets as os.environ values
        platform:     Override platform detection ('kaggle', 'colab', 'local')

    Returns:
        dict of {secret_name: secret_value}
    """
    if platform is None:
        platform = detect_platform()

    # Ensure SDK is installed
    _install_sdk()
    from infisical_sdk import InfisicalSDKClient

    # Get Infisical credentials from platform-native secrets
    client_id, client_secret = get_infisical_credentials(platform)

    if not client_id or not client_secret:
        raise ValueError(
            "INFISICAL_CLIENT_ID / INFISICAL_CLIENT_SECRET not found.\n"
            "Set them in Kaggle Secrets (Add-ons → Secrets) or "
            "Colab Secrets (🔑 sidebar) or as environment variables."
        )

    # Authenticate to Infisical
    client = InfisicalSDKClient(host="https://app.infisical.com")
    client.auth.universal_auth.login(
        client_id=client_id,
        client_secret=client_secret,
    )

    # Fetch all secrets from the specified path
    secrets_response = client.secrets.list_secrets(
        project_id=project_id,
        environment_slug=environment,
        secret_path=secret_path,
        view_secret_value=True,
    )

    result = {}
    for secret in secrets_response.secrets:
        result[secret.secretKey] = secret.secretValue
        if set_env_vars:
            os.environ[secret.secretKey] = secret.secretValue

    print(f"✅ Infisical: {len(result)} secrets loaded [{environment}/{secret_path}]", flush=True)
    print(f"   Keys: {list(result.keys())}", flush=True)
    return result


def load_all_secrets(platform=None):
    """
    High-level loader: reads INFISICAL_PROJECT_ID and INFISICAL_ENV
    from environment, then loads all secrets from Infisical.

    This is the main entry point for runner.py and notebook cells.
    Falls back to local env vars if Infisical is not configured.
    """
    if platform is None:
        platform = detect_platform()

    project_id = os.environ.get("INFISICAL_PROJECT_ID")
    environment = os.environ.get("INFISICAL_ENV", "dev")

    # If Infisical is configured, load from Infisical
    if project_id:
        print(f"🔐 Loading secrets from Infisical (project: {project_id}, env: {environment})...", flush=True)
        try:
            return load_infisical_secrets(
                project_id=project_id,
                environment=environment,
                platform=platform,
            )
        except Exception as e:
            print(f"❌ Infisical load failed: {e}", flush=True)
            print("⚠️ Falling back to platform-native secrets...", flush=True)

    # Fallback: load from platform-native secrets (legacy mode)
    if platform in ("kaggle", "colab"):
        print("🔑 Loading secrets from platform-native store (legacy fallback)...", flush=True)
        return _load_platform_secrets(platform)

    # Local: assume env vars are already set
    print("🔑 Using environment variables (local mode)", flush=True)
    return {}


def _load_platform_secrets(platform: str) -> dict:
    """
    Legacy fallback: load secrets directly from Kaggle/Colab native stores.
    Used when Infisical is not configured.
    """
    secret_keys = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "HF_TOKEN",
    ]

    result = {}

    if platform == "kaggle":
        from kaggle_secrets import UserSecretsClient
        client = UserSecretsClient()
        for key in secret_keys:
            try:
                val = client.get_secret(key)
                if val:
                    os.environ[key] = str(val)
                    result[key] = str(val)
                    print(f"  ✅ {key}", flush=True)
            except Exception:
                pass

    elif platform == "colab":
        from google.colab import userdata
        for key in secret_keys:
            try:
                val = userdata.get(key)
                if val:
                    os.environ[key] = str(val)
                    result[key] = str(val)
                    print(f"  ✅ {key}", flush=True)
            except Exception:
                pass

    if not result:
        print("  ⚠️ No secrets found!", flush=True)

    return result

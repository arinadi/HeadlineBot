"""
Infisical Secret Loader for HeadlineBot
========================================
Centralized secret management via Infisical Cloud REST API.
No external SDK needed — uses `requests` (already in requirements).

User stores 4 secrets in Kaggle/Colab:
  - INFISICAL_CLIENT_ID
  - INFISICAL_CLIENT_SECRET
  - INFISICAL_PROJECT_ID
  - INFISICAL_ENV (default: "dev")
"""

import os
import requests
from headlinebot.utils import detect_platform

INFISICAL_API = "https://app.infisical.com/api/v1"
def get_infisical_credentials(platform=None):
    """Retrieve Infisical credentials from platform-native secret stores."""
    if platform is None:
        platform = detect_platform()

    if platform == "kaggle":
        from kaggle_secrets import UserSecretsClient
        client = UserSecretsClient()
        return (
            client.get_secret("INFISICAL_CLIENT_ID"),
            client.get_secret("INFISICAL_CLIENT_SECRET"),
            client.get_secret("INFISICAL_PROJECT_ID"),
            client.get_secret("INFISICAL_ENV") or "dev",
        )

    elif platform == "colab":
        from google.colab import userdata
        return (
            userdata.get("INFISICAL_CLIENT_ID"),
            userdata.get("INFISICAL_CLIENT_SECRET"),
            userdata.get("INFISICAL_PROJECT_ID"),
            userdata.get("INFISICAL_ENV") or "dev",
        )

    else:
        return (
            os.environ.get("INFISICAL_CLIENT_ID"),
            os.environ.get("INFISICAL_CLIENT_SECRET"),
            os.environ.get("INFISICAL_PROJECT_ID"),
            os.environ.get("INFISICAL_ENV", "dev"),
        )


def _login(client_id, client_secret):
    """Authenticate via Universal Auth, return access token."""
    resp = requests.post(
        f"{INFISICAL_API}/auth/universal-auth/login",
        json={"clientId": client_id, "clientSecret": client_secret},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["accessToken"]


def _list_secrets(token, project_id, environment, secret_path="/"):
    """Fetch all secrets via REST API."""
    resp = requests.get(
        f"{INFISICAL_API.replace('/v1', '/v4')}/secrets",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "projectId": project_id,
            "environment": environment,
            "secretPath": secret_path,
            "viewSecretValue": "true",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("secrets", [])


def load_infisical_secrets(platform=None):
    """
    Load all secrets from Infisical Cloud via REST API.
    Returns dict of {secret_name: secret_value}.
    """
    client_id, client_secret, project_id, environment = get_infisical_credentials(platform)

    if not all([client_id, client_secret, project_id]):
        raise ValueError(
            "Missing Infisical credentials. Set in Kaggle/Colab Secrets:\n"
            "  INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET, INFISICAL_PROJECT_ID"
        )

    token = _login(client_id, client_secret)
    secrets = _list_secrets(token, project_id, environment)

    result = {}
    for s in secrets:
        key = s["secretKey"]
        val = s["secretValue"]
        os.environ[key] = val
        result[key] = val

    print(f"✅ Infisical: {len(result)} secrets loaded [{environment}]", flush=True)
    print(f"   Keys: {list(result.keys())}", flush=True)
    return result


def load_all_secrets(platform=None):
    """
    High-level loader. Reads INFISICAL_PROJECT_ID from platform-native secrets.
    Falls back to legacy platform-native loading if Infisical not configured.
    """
    if platform is None:
        platform = detect_platform()

    _, _, project_id, _ = get_infisical_credentials(platform)

    if project_id:
        print("🔐 Loading secrets from Infisical...", flush=True)
        try:
            return load_infisical_secrets(platform)
        except Exception as e:
            print(f"❌ Infisical failed: {e}", flush=True)
            print("⚠️ Falling back to platform-native secrets...", flush=True)

    if platform in ("kaggle", "colab"):
        print("⚠️ Infisical not configured. Platform-native secrets unavailable.", flush=True)
        return {}

    print("🔑 Using environment variables (local mode)", flush=True)
    return {}



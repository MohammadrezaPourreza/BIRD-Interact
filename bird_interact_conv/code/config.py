import os

# Auto-detect credentials path (Docker vs local)
_credential_path = "/app/bird_interact_conv/gcp_credentials/credentials.json"
if not os.path.exists(_credential_path):
    _credential_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gcp_credentials", "credentials.json")

model_config = {
    "model_name": {"base_url": "YOUR_API_URL", "api_key": "YOUR_API_KEY"},
    "gemini-2.5-pro": {"project": "sercan-v1", "location": "us-central1", "credential_path": _credential_path},
    "gemini-2.5-flash": {"project": "sercan-v1", "location": "us-central1", "credential_path": _credential_path},
    "gemini-2.0-flash": {"project": "sercan-v1", "location": "us-central1", "credential_path": _credential_path},
    "projects/618488765595/locations/us-central1/endpoints/897266359451254784": {"project": "sercan-v1", "location": "us-central1", "credential_path": _credential_path}
}

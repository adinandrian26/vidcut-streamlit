# VidCut Streamlit

Deploy via Streamlit Community Cloud.

## Secrets
Set the public Voice Clone API URL and its matching API key in Streamlit
secrets. Do not use localhost in cloud deployment.

```toml
VC_API_URL = "https://your-codespace-8520.app.github.dev"
VC_API_KEY = "the-same-value-as-the-backend-VC_API_KEY"
```

## Limitations
Chrome/Gemini automation and CapCut desktop integration require a local computer and are not available in Streamlit Cloud.

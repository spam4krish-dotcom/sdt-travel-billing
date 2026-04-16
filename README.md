# SDT Travel Billing Calculator

Internal tool for Specialised Driver Training — calculates NDIS non-labour travel costs.

## Deploy to Railway

See deployment instructions provided separately.

## Environment Variables (set in Railway)

| Variable | Value |
|---|---|
| `APP_PASSWORD` | Your chosen password |
| `GOOGLE_API_KEY` | Your Google Maps API key |
| `SECRET_KEY` | Any random string (for session security) |

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

# Deploy TriGuard on Render

This project is prepared for a paid Render Web Service and managed Render PostgreSQL in Singapore. The paid service is intentional: Render's Free Web Service does not allow outbound SMTP on port 587, and its Free Postgres database expires after 30 days.

## First deployment

1. Create a GitHub repository and push this project. Do not commit `.env`.
2. Sign in to [Render](https://dashboard.render.com/) with the GitHub account that can access the repository.
3. Select **New** → **Blueprint**, choose the repository, and select `render.yaml`.
4. Provide the required secret values when Render prompts for them:
   - `TRIGUARD_ADMIN_EMAIL` and a strong `TRIGUARD_ADMIN_PASSWORD`
   - `TRIGUARD_PUBLIC_BASE_URL`: `https://triguard-planner.onrender.com` if Render accepts the default service name; otherwise use the exact URL shown by Render.
   - `TRIGUARD_EMAIL_FROM`, `TRIGUARD_SMTP_HOST`, `TRIGUARD_SMTP_USERNAME`, and `TRIGUARD_SMTP_PASSWORD` from the chosen SMTP provider.
5. Create the Blueprint and wait for both the database and web service to become live.
6. Open `<your-url>/health`. It should report `"status": "healthy"`.
7. Create a test account and complete the verification email flow before sharing the URL publicly.

## Notes

- Keep SMTP, database, administrator, API-key, and session-secret values only in Render's secret settings—never in GitHub or `.env.example`.
- The blueprint chooses Render's `standard` web service (1 CPU / 2 GB RAM) and `basic-1gb` PostgreSQL tier. It is a sensible minimum for the Flask + scikit-learn application, but check Render's current pricing before creating the resources.
- After the first deployment, add your custom domain in Render. Then update `TRIGUARD_PUBLIC_BASE_URL` to that exact `https://` domain so verification links continue to work.
- The database retains account and assessment data. The local JSON audit file is not durable on a hosted container; use Render logs or a managed logging service for long-term audit retention.

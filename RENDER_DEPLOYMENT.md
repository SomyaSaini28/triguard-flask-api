# Deploy TriGuard on Render

This project is prepared for a free Render preview in Singapore. Self-signup is intentionally disabled in this mode, so the administrator account is the only login. Render's Free Web Service can sleep after inactivity, and its Free Postgres database expires after 30 days; use this setup for testing and demos only.

## First deployment

1. Create a GitHub repository and push this project. Do not commit `.env`.
2. Sign in to [Render](https://dashboard.render.com/) with the GitHub account that can access the repository.
3. Select **New** → **Blueprint**, choose the repository, and select `render.yaml`.
4. Provide the required secret values when Render prompts for them:
   - `TRIGUARD_ADMIN_EMAIL` and a strong `TRIGUARD_ADMIN_PASSWORD`
5. Create the Blueprint and wait for both the database and web service to become live.
6. Open `<your-url>/health`. It should report `"status": "healthy"`.
7. Create a test account and complete the verification email flow before sharing the URL publicly.

## Notes

- Keep SMTP, database, administrator, API-key, and session-secret values only in Render's secret settings—never in GitHub or `.env.example`.
- The blueprint chooses Render's Free web service and Free PostgreSQL tier for a preview. Free services are not a production data-retention plan.
- For public signup, change the plans to paid tiers, set `TRIGUARD_ALLOW_SELF_SIGNUP=true`, and add the HTTPS public URL plus SMTP variables from `.env.example`.
- After the first deployment, add your custom domain in Render. Then update `TRIGUARD_PUBLIC_BASE_URL` to that exact `https://` domain before enabling public signup.
- The database retains account and assessment data. The local JSON audit file is not durable on a hosted container; use Render logs or a managed logging service for long-term audit retention.

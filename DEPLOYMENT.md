# Furlong deployment and data safety

Furlong is not yet approved for public production deployment. Verify security and test results before enabling outside registrations.

## Environment
- Set `FURLONG_ENV=production` for any deployment reachable by testers. The app will refuse to start unless `FURLONG_SECRET_KEY` is set and `FURLONG_HTTPS=1` is configured. Configure TLS termination at the host/reverse proxy and verify HTTPS end to end; this setting alone does not provide TLS.
- Sessions use a 12-hour permanent-cookie lifetime after registration or login. Re-authentication is required after expiration.
- Registration is currently open to anyone who can reach the site. Do not expose the app publicly until the beta access policy is chosen and enforced.

- Set `FURLONG_SECRET_KEY` to a long random secret. Keep it stable between deployments and outside source control.
- Set `FURLONG_DATA_DIR` to a **persistent writable volume** that survives deploys and restarts. This is where `furlong.db` is stored. If unset, the local development database stays beside `app.py` for backward compatibility.
- Set `FURLONG_HTTPS=1` **only when users connect through HTTPS**; it enables Secure session cookies. Production must use HTTPS.
- Keep `FURLONG_CLAIM_LEGACY_TRIPS` unset for public registration. Only set it to `1` for a deliberate one-time migration of existing unowned local trips into the first account, then unset it.
- Keep `ENABLE_EUROPE_IMPORT` disabled. It is a development fixture, not a public feature.
- Do not run `python app.py` as a public server: the local development entry point enables debug mode. Use a production WSGI server and reverse proxy.

## Private beta invitations and email activation
- Production registration requires an unused invitation token tied to an email address; registration links use `/register?invitation=TOKEN`.
- Invitation records live in the `beta_invitations` SQLite table. From a trusted administrator shell with access to the persistent database, run `python scripts/issue_beta_invitation.py tester@example.com` after setting `FURLONG_PUBLIC_URL`. The command prints a private registration URL. Deliver it directly to the intended tester; never post it publicly or include it in logs. Invitations expire after seven days and issuing a new one replaces unused invitations for the same email. No public invitation-creation endpoint exists.
- Set `FURLONG_PUBLIC_URL` to the exact public HTTPS origin (for example `https://your-domain.example`).
- Configure `FURLONG_SMTP_HOST`, `FURLONG_SMTP_PORT` (default 587), `FURLONG_SMTP_USERNAME`, `FURLONG_SMTP_PASSWORD`, and `FURLONG_SMTP_FROM` as deployment secrets.
- SMTP must support authenticated STARTTLS. Never commit passwords or invitation/activation tokens.
- Email activation links expire after 24 hours and can be used only once. Unverified accounts cannot sign in to production.
- **Beta launch blocker:** add safe activation-email resend/recovery, administrator invitation issuance, and complete end-to-end tests. A failed SMTP send currently leaves an unverified account that requires administrator recovery.

## Backups
Run `python scripts/backup_database.py /path/to/offsite-backups` on a schedule. The script uses SQLite's online backup API, verifies integrity, and creates a private file. Store backups outside the app and database volume, with retention and access controls. Test recovery using `python scripts/verify_restore.py /path/to/backup.db`, which copies into a temporary database and checks integrity and required tables. This **does not replace the live database**.

## Release checks
1. Run `python -m unittest discover -s tests -v` and resolve failures.
2. Confirm HTTPS, stable secret, cookie configuration, and a persistent data volume.
3. Verify registration, login, logout, CSRF rejection, cross-account access, and backup/restore.
4. Confirm backup scheduling, retention, and offsite storage with the chosen host.
5. Perform an actual fresh-deployment smoke test before inviting beta testers.

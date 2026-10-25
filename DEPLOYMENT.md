# Furlong deployment and data safety

Furlong is not yet approved for public production deployment. Verify security and test results before enabling outside registrations.

## Environment
- Set `FURLONG_SECRET_KEY` to a long random secret. Keep it stable between deployments and outside source control.
- Set `FURLONG_DATA_DIR` to a **persistent writable volume** that survives deploys and restarts. This is where `furlong.db` is stored. If unset, the local development database stays beside `app.py` for backward compatibility.
- Set `FURLONG_HTTPS=1` **only when users connect through HTTPS**; it enables Secure session cookies. Production must use HTTPS.
- Keep `ENABLE_EUROPE_IMPORT` disabled. It is a development fixture, not a public feature.
- Do not run `python app.py` as a public server: the local development entry point enables debug mode. Use a production WSGI server and reverse proxy.

## Backups
Run `python scripts/backup_database.py /path/to/offsite-backups` on a schedule. The script uses SQLite's online backup API, verifies integrity, and creates a private file. Store backups outside the app and database volume, with retention and access controls. Test recovery using `python scripts/verify_restore.py /path/to/backup.db`, which copies into a temporary database and checks integrity and required tables. This **does not replace the live database**.

## Release checks
1. Run `python -m unittest discover -s tests -v` and resolve failures.
2. Confirm HTTPS, stable secret, cookie configuration, and a persistent data volume.
3. Verify registration, login, logout, CSRF rejection, cross-account access, and backup/restore.
4. Confirm backup scheduling, retention, and offsite storage with the chosen host.
5. Perform an actual fresh-deployment smoke test before inviting beta testers.

# Security

This is a static site. A build reads the feed list and the saved links, fetches public RSS and Atom feeds, and writes HTML files. There is no application server and no database. The host serves the files it just built.

What that means in practice:

- The page has no accounts of its own and no login form.
- Saved links are accepted only from an issue opened by the repository owner, and only when that issue has the `add-link` label. Issues opened by anyone else are ignored.
- A link must be `http://` or `https://`. Other schemes are rejected.
- Titles, notes, and feed text are treated as data. HTML in a summary is stripped, and text is escaped before it is shown.
- The deploy hook address lives only in the repository secret `VERCEL_DEPLOY_HOOK_URL`. It is not written in the repository and the refresh workflow does not print it.
- The build runs on Python 3.12. It downloads one pip wheel, checks that wheel's sha256, and installs `requirements.txt` with `--require-hashes`. It does not install packages from the operating system.

## Reporting a vulnerability

Please report a security problem in private. On GitHub, open the repository's **Security** tab, then **Advisories**, then **Report a vulnerability**. Do not open a public issue for a security report.

If private advisories are not available on your copy, contact the repository owner directly.

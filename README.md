# Read it later library

A small website that collects recent articles from news feeds you choose, plus links you save yourself. GitHub stores the list. On a schedule, GitHub asks [Vercel](https://vercel.com) to rebuild the page. Vercel publishes ordinary files. There is no server to look after and no database.

The example list has two topics and six public feeds, so the first build already shows articles. Replace them with the feeds you actually want.

## Use this template

1. Open this repository on GitHub.
2. Click **Use this template**, then **Create a new repository**.
3. Pick a name. Choose **Private** or **Public** (the next section explains the difference).
4. Click **Create repository**.
5. Follow the rest of this guide in *your* new repository, not in the template.
6. Before you edit any file in the browser, open your GitHub account **Settings** (your avatar, then **Settings**), then **Emails**, and tick **Keep my email addresses private**. A web edit is a commit. With that ticked, GitHub records a private noreply address instead of a personal one.
7. If you want other people to copy *your* repository the same way, open the repository **Settings**, then **General**, and tick **Template repository**.

If you do not see **Use this template**, the repository has not been marked as a template yet. The owner does that under [Mark this repository as a template](#mark-this-repository-as-a-template).

## Keep the copy private or public

**Private repository, public website.** People cannot browse your files. They *can* read the finished page: headlines from the feeds, and any link or note you saved. Do not save something you would not put on a noticeboard. This is the usual choice.

**Private repository, and a private website.** Same as above, plus [Vercel Authentication](#optional-keep-the-site-private) so visitors have to sign in. The files stay in a private repository as well.

**Public repository.** Anyone can read `feeds.yml` and `saved-links.json`, including notes. The Add link action still ignores issues opened by other people, but those issues sit in the list until you close them. A public repository is easier to share, and GitHub's secret scanning is included for free. Do not put private notes in saved links. GitHub also pauses the scheduled refresh after 60 days with no activity in a public repository. A private repository does not get that pause. See [Turn on Actions and refresh once](#turn-on-actions-and-refresh-once).

The deploy hook, described below, must stay secret either way.

## Edit your feeds

You can do this in the browser.

1. Open your repository.
2. Click `feeds.yml`.
3. Click the pencil icon (**Edit this file**).
4. Each topic is a block under `topics:`. Each feed inside it has a `name` and a `url`. `region` and `country` are optional labels.
5. To add a topic, copy a whole block, including the line that starts with `- name:`, and change the name. The page grows a new filter chip for that name on the next build. You do not edit the script.
6. Scroll down, choose **Commit changes**, leave **Commit directly to the `main` branch** selected, and confirm.

A feed address must start with `https://` or `http://`. Keep the quotes around it.

```yaml
topics:
  - name: "News"
    feeds:
      - name: "BBC News"
        url: "https://feeds.bbci.co.uk/news/rss.xml"
        country: "United Kingdom"
```

`config.yml` is the same kind of edit. It holds the page title, how many articles to keep from each feed (`per_feed_cap`), how many days to look back (`max_age_days`), and the clock (`timezone`, `locale`). `refresh_hours` is the number printed on the page. The real timetable is the schedule in `.github/workflows/refresh.yml` (`17 */5 * * *`, which is 00:17, 05:17, 10:17, 15:17 and 20:17 UTC). If you change one, change the other.

## Put the site on Vercel

The free Hobby plan is enough. You do not need a paid plan.

1. Sign in at [vercel.com](https://vercel.com) with your GitHub account and choose the Hobby plan.
2. Click **Add New…**, then **Project**.
3. Import the Git repository you just created. If it is missing, choose **Adjust GitHub App Permissions** on that screen and allow this repository, then come back and import it.
4. Leave the root directory as the repository root.
5. Set the framework preset to **Other**. Vercel reads `vercel.json`. Check the build settings match this:

| Setting | Value |
|---|---|
| Install command | leave empty |
| Build command | `curl -fsSL -o /tmp/pip.whl https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl && echo "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70  /tmp/pip.whl" | sha256sum -c - && PYTHONPATH=/tmp/pip.whl python3.12 -m pip install --require-hashes --target .pydeps -r requirements.txt && PYTHONPATH=.pydeps python3.12 scripts/build.py` |
| Output directory | `_site` |

6. Click **Deploy**. The first deploy is the first build. When it finishes, Vercel shows a production address. Open it. You should see the library.

`_site/` is produced during the build. Do not commit that folder.

## Create the deploy hook

Feeds change even when the files do not, so GitHub needs a way to ask Vercel for a fresh build. That way is a deploy hook. The address is a password: anyone who has it can start a rebuild (they cannot edit the site). It must live only in a **repository secret**. Do not put it in a file, an issue, a chat, or an environment secret.

1. In the Vercel project, open **Settings**, then **Git**, then **Deploy Hooks**.
2. Name it `refresh`, choose the `main` branch, and create it.
3. Copy the address once. You will not need to look at it again.
4. On GitHub, open your repository, then **Settings**, then **Secrets and variables**, then **Actions**.
5. Click **New repository secret**. The name is exactly `VERCEL_DEPLOY_HOOK_URL`. Paste the address. Save.
6. Do not create a GitHub Environment, and do not put this under **Environment secrets**. The workflow reads the repository secret.

## Turn on Actions and refresh once

1. Open the **Actions** tab. If GitHub asks you to enable Actions, enable them.
2. Click **Refresh library** in the left-hand list.
3. Click **Run workflow**, leave the branch as `main`, and click **Run workflow** again.
4. Open the run. The rebuild step should say `Deploy hook accepted.` It must not print the hook address. Vercel then starts a build on its own. A minute or two later, reload the site.

After that, the schedule runs every five hours. Your computer does not need to be on. If the secret is missing, the run still succeeds and writes a notice that the rebuild was skipped, and the site is not updated.

GitHub pauses scheduled workflows in a **public** repository after 60 days with no activity (no commits, issues, or pull requests). The site then stops refreshing until you open the **Actions** tab, click **Refresh library**, and click **Enable workflow**. A private repository is not paused this way. If you want the five-hour schedule to keep running without a visit, keep the repository private.

Saving a link commits a file, and Vercel rebuilds on that commit. The schedule does not have to run for a saved link to show up.

## Optional: your own web address

In the Vercel project, open **Settings**, then **Domains**, and add a domain you own. Vercel shows the DNS records to set at the company you bought the domain from. The Hobby plan supports this. Skip this if the address Vercel gave you is enough.

## Optional: keep the site private

By default the production site is public. Preview addresses stay protected by Vercel's standard protection.

To require a sign-in for the production site as well, open the project, then **Settings**, then **Deployment Protection**, and turn on **Vercel Authentication**. Only people you allow can open the page. This does not hide a public GitHub repository. If the repository is public, the files are still public there.

## Save a link

Saved links and notes are copied onto the page. Do not save anything private.

### With an issue

The action only runs when **both** of these are true: the issue was opened by the GitHub account that owns the repository, and the issue has the label `add-link`. Issues from anyone else are ignored and stay open until you close them.

Create that label once before the first save. A template does not copy labels into a new repository. Without a label named exactly `add-link`, the form still opens, you can submit it, and nothing is saved.

1. Open **Issues**, then **Labels**, then **New label**.
2. Set the name to `add-link`. The colour does not matter. Save the label.

Then save a link:

1. Sign in to GitHub as the owner of the repository.
2. Open **Issues**, then **New issue**, then **Add link**.
3. Paste the address. Title, topic, and note are optional.
4. Click **Submit new issue**. Within a few minutes the action saves it, closes the issue, and Vercel rebuilds.

The topic is a tag on that saved link. It does not have to match a heading in `feeds.yml`. Saved links are listed under **Saved links**.

### With a bookmarklet

A bookmarklet is a bookmark that opens the Add link form with the page you are reading already filled in. You stay signed in to GitHub. No token is stored in the bookmark.

1. Create a bookmark in your browser. The name can be `Save for later`.
2. Edit the bookmark's address and replace it with the line below.
3. Replace both `YOUR-USERNAME` and `YOUR-REPO` with your GitHub username and repository name. Leave the rest alone.

```
javascript:location.href='https://github.com/YOUR-USERNAME/YOUR-REPO/issues/new?template=add-link.yml&title='+encodeURIComponent('Add: '+document.title)+'&link='+encodeURIComponent(location.href)+'&link_title='+encodeURIComponent(document.title)
```

Click the bookmark on an article. GitHub opens the form. Check it, then click **Submit new issue**.

On an iPhone, a Shortcut can do the same job: receive a URL from the share sheet, URL-encode it, then open `https://github.com/YOUR-USERNAME/YOUR-REPO/issues/new?template=add-link.yml&link=` followed by that encoded address. Tap **Submit new issue**.

You can also open this address and add the encoded link on the end:

```
https://github.com/YOUR-USERNAME/YOUR-REPO/issues/new?template=add-link.yml&link=
```

## Feeds that stop working

A feed that fails, or whose newest article is older than `max_age_days`, is not silent.

- On the page, open **Feeds needing attention** at the bottom. Each row names the feed, the topic, and what went wrong (for example a dead address, or a stale date).
- In the build log on Vercel, the same feeds are printed as `DEAD/STALE`, and the log starts that block with `WARNING:` when any feed needs attention.

Fix one by editing `feeds.yml` (correct the address, or delete that feed) and committing. The next deploy picks it up.

## Secure your copy

Do these once, in your repository's **Settings**.

**Stop `main` being force-pushed or deleted.** Open **Rules**, then **Rulesets**, then **New ruleset**, then **New branch ruleset**. Name it `protect main`. Target the default branch. Turn on **Block force pushes** and **Restrict deletions**. Do **not** turn on "Require a pull request before merging". The Add link action commits straight to `main`. If you want that rule anyway, add a bypass for `github-actions[bot]`, or saving a link will fail. On the free plan, rulesets are included for public repositories. If the screen is missing on a private repository, the plan does not include it.

**Secret scanning and push protection.** Open **Code security** (on some accounts this sits under **Advanced Security**). Turn on **Dependabot alerts** and **Dependabot security updates**. Turn on **Secret scanning** and **Push protection** when GitHub shows them. Public repositories include secret scanning for free. On a private personal repository those two switches are often missing unless the plan includes GitHub Secret Protection. Dependabot alerts are available either way. This repository also has `.github/dependabot.yml`, so once a week GitHub may open a pull request that only bumps a pinned tool version. Read it and merge it. You do not have to, and the site keeps refreshing if you don't.

**Actions.** Open **Actions**, then **General**.

- Under **Workflow permissions**, choose **Read repository contents**. The Add link job asks for write access in its own file, which is allowed. Leave the default as read.
- Under **Fork pull request workflows**, choose **Require approval for all external contributors**. On a private repository, tick **Require approval for fork pull request workflows**, and do not tick **Send write tokens to workflows from pull requests**. This file does not run on pull requests at all. The setting is there so a workflow added later cannot run from a fork without you approving it.

**The hook stays a secret.** `VERCEL_DEPLOY_HOOK_URL` is a repository secret. Never paste it into the README, an issue, a log, or a screenshot. If it leaks, rotate it:

1. In Vercel, under **Settings**, then **Git**, then **Deploy Hooks**, create a new hook for `main` and copy the new address.
2. Delete the old hook. The old address stops working.
3. On GitHub, under **Settings**, then **Secrets and variables**, then **Actions**, update `VERCEL_DEPLOY_HOOK_URL` with the new address.
4. Run **Refresh library** once. The log should say the hook was accepted, and it should not show the address.

## Mark this repository as a template

Do this on the repository that other people should copy (the original, or your own copy if you want it to be a template too).

1. Open **Settings**, then **General**.
2. Tick **Template repository**.
3. Save. **Use this template** then appears for people who can see the repository. A private template can be copied by you. A public template can be copied by anyone with an account.

## Troubleshooting

**The Actions list is empty.** Open **Settings**, then **Actions**, then **General**, and allow Actions.

**The refresh run says the rebuild was skipped.** The repository secret is missing or misnamed. The name is exactly `VERCEL_DEPLOY_HOOK_URL`, and it is a repository secret, not an environment secret.

**The hook step failed.** The address was rejected. Rotate it using the steps above. The log does not print the address on purpose.

**The page has a heading but no articles.** Open the deployment on Vercel and read the build log. Look for `DEAD/STALE`. A browser extension that blocks scripts will also leave the list empty.

**An Add link issue stayed open and nothing was saved.** You were not signed in as the account that owns the repository, or the label `add-link` does not exist. Templates do not copy labels, and without that exact name the form does nothing. Create it under **Issues**, then **Labels**, then **New label**. Only the repository owner is accepted. Close a stray issue yourself.

**A saved link never appears.** Give Vercel a couple of minutes after the action commits. Then reload. The link's address must start with `https://` or `http://`.

**The bookmarklet opens a blank GitHub page.** Edit the bookmark and replace `YOUR-USERNAME/YOUR-REPO` with your real repository. The form file is `add-link.yml`.

**I changed `refresh_hours` and the site still updates on the old timetable.** The number on the page is only a label. The timetable is the `cron` line in `.github/workflows/refresh.yml`.

## Try a build on your own computer

You do not need this for the hosted site.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build.py
```

Open `_site/index.html` in a browser. That folder is gitignored. Do not commit it.

`tools/test_feeds.py` checks a tab-separated list of candidate feeds (topic, region, country, name, url) before you add them. It is optional.

## Files

| File | What you do with it |
|---|---|
| `feeds.yml` | Your feeds, grouped by topic. Edit this. |
| `config.yml` | Title, caps, age, and clock. Edit this. |
| `saved-links.json` | Links you saved. The issue form writes it. The `_format` key explains the fields. |
| `scripts/build.py` | Fetches feeds and writes the page. Leave it unless you mean to change the builder. |
| `scripts/add_link_from_issue.py` | Turns an owner issue into a saved link. |
| `assets/` | The page, the cottagecore theme, and the script. They are inlined into the page. |
| `vercel.json` | Build command, output folder, and security headers. |
| `.github/workflows/refresh.yml` | The five-hour schedule, the manual run, and the Add link action. |
| `.github/ISSUE_TEMPLATE/add-link.yml` | The Add link form. |
| `requirements.txt` | Exact Python package versions, each with a sha256 hash. |
| `SECURITY.md` | What this site is, and how to report a security problem. |

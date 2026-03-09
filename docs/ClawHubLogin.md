# ClawHub login and "Missing state"

When you run `clawhub login` (from the command line or from the Companion app), the CLI opens a browser for GitHub OAuth. After you authorize, GitHub redirects back to a **local callback server** run by the CLI (e.g. `http://127.0.0.1:.../auth/callback`). The redirect URL includes a `state` parameter that must match the value the CLI stored when it started the flow. If it doesn’t match—or the callback never reaches the CLI—you see:

```text
CLI login
Missing state.
Run the CLI again to start a fresh login.
```

## Why "Missing state" happens

- **Callback never reaches the CLI** — Firewall, antivirus, or another app using the callback port can block or intercept the redirect. The CLI never receives the request, or it receives it without the expected state.
- **Redirect goes to the wrong place** — If you open the login URL on a **different device** (e.g. phone) instead of on the **machine running Core**, the browser redirects on that device; the CLI on the Core machine never gets the callback.
- **Two login attempts at once** — Running `clawhub login` twice (e.g. terminal + Companion) can overwrite or confuse the stored state so the first flow fails.
- **Browser or security software** — Some browsers or extensions block redirects to `localhost` / `127.0.0.1`; the CLI may require a specific loopback URL.

## What to try

1. **Run only one login**  
   Don’t start `clawhub login` from both the terminal and the Companion at the same time. Wait for one attempt to finish or time out, then try again once.

2. **Complete the flow on the Core machine**  
   When the browser opens, finish the GitHub authorization on **the same computer where Core (and the CLI) are running**. Do not open the login link on another device.

3. **Use token login (workaround)**  
   If the browser flow keeps failing, use the CLI’s token-based login so there is no local callback:

   - Open **https://clawhub.ai** in a browser and sign in with GitHub.
   - In the site, find where to get a **CLI token** (e.g. account or developer settings).
   - On the **machine running Core**, in a terminal:

     ```bash
     clawhub login --no-browser --token YOUR_TOKEN
     ```

   Replace `YOUR_TOKEN` with the token you got from clawhub.ai. After that, `clawhub whoami` should show you as logged in and search/install from the Companion will use that session.

4. **Check port and firewall**  
   The CLI starts a small HTTP server for the callback (port may vary; often in the 14xx range). If you use a strict firewall or antivirus, allow that process to listen on loopback.

5. **Update ClawHub CLI**  
   Newer versions may improve OAuth or callback handling:

   ```bash
   npm i -g clawhub@latest
   ```

## HomeClaw behavior

- When you tap **Login to ClawHub** in the Companion, Core runs `clawhub login` on the **Core machine**. The browser must open **there**, and you must complete the flow **there**.
- If you are **already logged in** (`clawhub whoami` succeeds), Core skips opening the browser and reports “Already logged in.”
- The “Missing state” message comes from the **ClawHub CLI**, not from HomeClaw. Using **token login** (step 3 above) avoids the callback and usually fixes the issue when the browser flow keeps failing.

## Token in config (core.yml)

You can put your ClawHub token in **config/core.yml** so Core logs in automatically and search/install work without using the browser or pasting the token in the Companion:

```yaml
clawhub_token: "YOUR_TOKEN_FROM_CLAWHUB_AI"
```

After you add it, restart Core. Core will use this token to log in to the ClawHub CLI when needed (e.g. when you check login status, search, or install from the Companion). Restrict permissions on `config/core.yml` if the token is sensitive.

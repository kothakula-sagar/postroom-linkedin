# Postroom · LinkedIn Studio

A single-user publishing desk for a personal LinkedIn profile. Compose text posts, preview them, save a browser draft, publish publicly, or schedule with a local SQLite queue. No third-party packages are required.

## Try the interface

On GitHub, open repository **Settings → Pages**. Select **Deploy from a branch**, then choose **main** and **/ (root)**. The Pages preview supports composing, previewing and saving a draft. Run the Python server below for real LinkedIn publishing. GitHub Pages serves static files and cannot run Python or store your client secret.

## Connect your account

1. Install Python 3.10 or later. Download or clone this repository and open a terminal in it.
2. Create an app in the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps). Complete any LinkedIn Page association or verification the portal requests. The tool still publishes to the signed-in personal profile.
3. In the app's Products tab, enable **Sign In with LinkedIn using OpenID Connect** and **Share on LinkedIn**.
4. In the Auth tab, register `http://127.0.0.1:8787/callback` as an authorized redirect URL.
5. Copy `.env.example` to `.env` and fill in your client ID and secret from the Auth tab. Keep this file on your computer.
6. Run `python server.py` (or `python3 server.py`), open [Postroom](http://127.0.0.1:8787), and click **Connect LinkedIn**.

## Publish or schedule

**Publish now** asks you to confirm a public post. **Schedule** uses the time zone of your browser. Keep the server running and online at the scheduled time. Overdue items run when the server starts again with a valid connection for the same profile. You can cancel a scheduled post from its queue. Disconnecting cancels pending posts for the current profile and removes its local token. To revoke the provider grant, use LinkedIn's account settings.

A queue item marked **Check LinkedIn** means the server could not confirm publication. Check your LinkedIn activity before retrying. If your authorization expires, connect again. The local SQLite file contains queued post text and a LinkedIn access token. Keep it private, and run the app only on the loopback address on a trusted computer.

Official API setup: [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin).

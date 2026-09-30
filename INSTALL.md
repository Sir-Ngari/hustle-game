# Hustle to a Billion: install guide

This puts the game online at your own web address, for example `https://game.denriafrica.com`, with:

- **The game** at `https://game.denriafrica.com`. Players create an account with a username and password, and their empire is saved on your server.
- **The admin dashboard** at `https://game.denriafrica.com/admin`, protected by a password only you know.

It runs next to Odoo on your DigitalOcean droplet without touching it. It has its own system user, its own folder (`/opt/hustle`), its own port (8090, reachable only from inside the server) and its own web address. It needs no extra software apart from nginx, which you may already have.

Every command below says **what it does** and **what you should see**. Run them one at a time in the DigitalOcean browser console. Wherever you see `game.denriafrica.com`, use the address you choose in Step 1.

---

## Step 1: Choose the web address (at your domain provider)

In the DNS settings for `denriafrica.com`, add a record:

| Type | Name | Value |
|---|---|---|
| A | `game` | your droplet's IP address (shown on the droplet page in DigitalOcean) |

DNS changes can take anywhere from a few minutes to an hour. You can carry on with Steps 2 to 5 while you wait.

---

## Step 2: Put the code on GitHub (on your computer)

1. Unzip `hustle-game.zip`.
2. On github.com, click **New repository**. Name it `hustle-game`, choose **Public** and click **Create repository**. The code contains no passwords; your admin password lives only on the server.
3. On the new repository's page, click **uploading an existing file**. Drag **everything inside** the unzipped folder onto the page (`server.py`, `INSTALL.md` and the `public`, `deploy` and `build` folders), then click **Commit changes**.

If you'd rather keep the repository private, that works too. In Step 3, GitHub will then ask for your username and a personal access token instead of your password.

---

## Step 3: Install the game on the server (DigitalOcean console)

**3.1 Check Python**

```bash
python3 --version
```
*What it does:* shows the Python version that the game will use (Odoo already uses it).
*What you should see:* `Python 3.8` or newer, for example `Python 3.10.12`.

**3.2 Create a separate system user for the game**

```bash
sudo adduser --system --group --home /opt/hustle hustle
```
*What it does:* creates a locked-down user called `hustle` that runs the game, so the game can't touch Odoo or anything else.
*What you should see:* a few lines ending in `Creating home directory '/opt/hustle'`. (If it says the user already exists, that's fine.)

**3.3 Download the code**

```bash
sudo git clone https://github.com/YOUR-GITHUB-USERNAME/hustle-game.git /opt/hustle/app
```
*What it does:* copies your repository into `/opt/hustle/app`. Replace `YOUR-GITHUB-USERNAME`.
*What you should see:* `Cloning into '/opt/hustle/app'...` then `done.`
*If it says `git: command not found`:* run `sudo apt update && sudo apt install -y git`, then run the clone command again.

**3.4 Create the data folder and hand both folders to the game user**

```bash
sudo mkdir -p /opt/hustle/data && sudo chown -R hustle:hustle /opt/hustle
```
*What it does:* makes the folder where the player database will live, and makes the `hustle` user its owner.
*What you should see:* nothing. No output means it worked.

**3.5 Set your admin password**

```bash
sudo cp /opt/hustle/app/deploy/hustle.env.example /etc/hustle.env && sudo chmod 600 /etc/hustle.env && sudo nano /etc/hustle.env
```
*What it does:* creates the settings file, makes it readable only by the system, and opens it in the nano editor.
*What you should see:* the settings file in the editor. Change `change-this-to-a-long-password` to your own admin password (at least 10 characters). Press **Ctrl+O** then **Enter** to save, and **Ctrl+X** to exit.

**3.6 Start the game as a service**

```bash
sudo cp /opt/hustle/app/deploy/hustle.service /etc/systemd/system/hustle.service && sudo systemctl daemon-reload && sudo systemctl enable --now hustle
```
*What it does:* registers the game as a service, starts it now, and makes it start automatically whenever the server reboots.
*What you should see:* `Created symlink /etc/systemd/system/multi-user.target.wants/hustle.service → /etc/systemd/system/hustle.service.`

**3.7 Check it's running**

```bash
sudo systemctl status hustle --no-pager
```
*What it does:* shows the service's state.
*What you should see:* a green `active (running)` line, and near the bottom `Hustle to a Billion is running on http://127.0.0.1:8090`.
*If it says `failed`:* run `sudo journalctl -u hustle -n 30 --no-pager` and send me the output.

```bash
curl -s http://127.0.0.1:8090/healthz
```
*What it does:* asks the game server if it's alive, from inside the droplet.
*What you should see:* `{"ok":true}`

---

## Step 4: Connect it to the web with nginx

**4.1 Check whether nginx is already installed**

```bash
nginx -v
```
*What it does:* shows the nginx version if nginx is installed.
*What you should see:* either `nginx version: nginx/1.x.x` (installed, go to 4.2), or `command not found`. In that case install it:

```bash
sudo apt update && sudo apt install -y nginx
```
*What it does:* installs the nginx web server.
*What you should see:* a long install log ending with no errors.

**4.2 Add the game's site**

```bash
sudo cp /opt/hustle/app/deploy/nginx-hustle.conf /etc/nginx/sites-available/hustle && sudo sed -i 's/game.example.com/game.denriafrica.com/' /etc/nginx/sites-available/hustle && sudo ln -sf /etc/nginx/sites-available/hustle /etc/nginx/sites-enabled/hustle
```
*What it does:* installs the site settings and puts your web address in them. If you chose a different address in Step 1, change `game.denriafrica.com` in this command first.
*What you should see:* nothing. No output means it worked.

**4.3 Check the settings, then reload nginx**

```bash
sudo nginx -t && sudo systemctl reload nginx
```
*What it does:* tests every nginx site for mistakes and, only if the test passes, reloads nginx. Your Odoo site keeps running throughout.
*What you should see:* `syntax is ok` and `test is successful`.
*If you see an error instead:* nginx does not reload, so nothing breaks. Send me the message.

**4.4 Open the firewall for web traffic (only if the firewall is on)**

```bash
sudo ufw status
```
*What it does:* shows whether the Ubuntu firewall is active.
*What you should see:* `Status: inactive` (nothing to do), or `Status: active` with a list of rules. If it's active and there's no line for `Nginx Full` or ports 80 and 443, run:

```bash
sudo ufw allow 'Nginx Full'
```
*What you should see:* `Rule added`.

---

## Step 5: Turn on HTTPS

Do this once your DNS record from Step 1 is working (you can check by opening `http://game.denriafrica.com`: you should see the game's "Connecting" screen or a security warning, not "site can't be reached").

```bash
sudo apt install -y certbot python3-certbot-nginx
```
*What it does:* installs Let's Encrypt's free certificate tool.
*What you should see:* an install log ending with no errors (or "already the newest version").

```bash
sudo certbot --nginx -d game.denriafrica.com
```
*What it does:* gets a free HTTPS certificate for the game's address and sets nginx up to use it. It renews itself automatically.
*What you should see:* questions for your email and agreement to the terms, then `Congratulations! You have successfully enabled HTTPS on https://game.denriafrica.com`.

---

## Step 6: Try it

1. Open `https://game.denriafrica.com`, create an account and play a few months.
2. Open `https://game.denriafrica.com/admin` and log in with your admin password. You should see yourself in the player list and your moves in the live activity feed.
3. Share `https://game.denriafrica.com` with your players. Don't share `/admin`.

---

## Looking after it

**Update the game after new changes are pushed to GitHub.**

```bash
cd /opt/hustle/app && git pull && sudo systemctl restart hustle && sleep 2 && systemctl is-active hustle
```
*What it does:* downloads the latest version from your GitHub repository and restarts the game. Players' accounts and saves are untouched; they live in `/opt/hustle/data`.
*What you should see:* a list of changed files, then `active`.

**Back up the player database.**

```bash
sudo -u hustle python3 -c "import sqlite3,time;s=sqlite3.connect('/opt/hustle/data/hustle.db');d=sqlite3.connect('/opt/hustle/data/backup-'+time.strftime('%Y%m%d')+'.db');s.backup(d);print('backup saved')"
```
*What it does:* makes a safe copy of the database while the game keeps running.
*What you should see:* `backup saved`. The copy is in `/opt/hustle/data`, named with today's date.

**See recent server messages** (if something seems wrong):

```bash
sudo journalctl -u hustle -n 50 --no-pager
```

**Change the admin password.** Edit it with `sudo nano /etc/hustle.env`, then run `sudo systemctl restart hustle`.

---

## What the admin dashboard shows

- **Headline numbers:** total players, active today, active this week, new sign-ups, game months played, billionaires and bankruptcies.
- **Daily active players** for the last 14 days. Hover over a bar to also see that day's sign-ups.
- **Live activity:** the latest moves across all players, straight from their in-game news.
- **Players table:** search, sort and filter (online now, active today, billionaires, bankrupt, disabled).
- **Player detail:** click anyone to see their stats, net worth over time, their last 200 moves, and to **disable**, **re-enable**, **reset their game** or **delete** their account.

The page refreshes itself every 30 seconds.

## How it's protected

- Passwords are stored as salted PBKDF2 hashes, never as plain text.
- Log-ins use secure, HTTP-only cookies over HTTPS.
- Repeated wrong passwords are slowed down: 10 tries per 10 minutes for players, 5 per 15 minutes for admin.
- The admin area has its own password, set only on the server.
- The game server listens only inside the droplet, so everything reaches it through nginx and HTTPS.
- It runs as its own locked-down user that can write to nothing except its data folder.

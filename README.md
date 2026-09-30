# Hustle to an Empire

A turn-based entrepreneur life sim: build an empire from a street hustle to $1B across business, property, sport, politics and philanthropy.

- `server.py`: the game server (Python 3.8+, standard library only, SQLite)
- `public/index.html`: the game
- `public/admin.html`: the admin dashboard (at `/admin`)
- `deploy/`: service, nginx and settings files
- `build/`: how `public/index.html` is generated from the Claude artifact version

**To install on a server, follow [INSTALL.md](INSTALL.md).**

To try it on your own computer: `HUSTLE_SECURE_COOKIES=0 HUSTLE_ADMIN_PASSWORD=choose-a-password python3 server.py`, then open http://127.0.0.1:8090

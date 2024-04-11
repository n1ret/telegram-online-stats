# telegram-online-stats
Python telegram self bot for dialogs online scrapping

**All data will be stored in postgres db**

## Setup

- Install packages

```sh
# Ubuntu
apt install python3 python3-venv postgresql

# Arch linux
pacman -S python postgresql
```

- Clone repo, step in

```sh
git clone https://github.com/n1ret/telegram-online-stats.git
cd telegram-online-stats
```

- Rename `template.env` to `.env`. Insert API_ID, API_HASH from https://my.telegram.org. Insert postgres creditionals.

- Create python virtual env and install libs

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

- Run script

```sh
.venv/bin/python main.py 
```

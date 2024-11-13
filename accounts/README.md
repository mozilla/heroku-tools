# Tools for working with Heroku

The scripts here are used to manage membership in our Heroku account.

Actually, the ancient bash scripts have been retired, and all functionality is
in a single Python script. That package is [`uv`][uv] friendly, so to see the
current features, just
```bash
❯ uv run acnt-mgmt.py --help
Reading inline script metadata from `acnt-mgmt.py`
usage: acnt-mgmt.py [-h] [--token TOKEN] [--team TEAM] [--clip] [--no-clip] {list,emails,verify,revoke} ...

options:
  -h, --help            show this help message and exit
  --token TOKEN         Heroku Auth Token or op url [env: HEROKU_TOKEN=]
  --team TEAM           Heroku team to query (default mozillacorporation) [env: HEROKU_TEAM=]
  --clip                Place output on clipboard (default False) [env: HEROKU_USE_CLIPBOARD=]
  --no-clip             Place output on clipboard (default False) [env: HEROKU_USE_CLIPBOARD=]

Supported Actions:
  various commands that can be performed (some may have options, check their --help)

  {list,emails,verify,revoke}
    list                list all problem members
    emails              list all emails
    verify              verify membership of supplied emails
    revoke              revoke membership of supplied emails
```
Some of the actions have options, using `--help` at that level will provide
more information.

## Installation

The script `acnt-mgmt.py` is a single file with inline script metadata. Which
means you can invoke it from [`uv`][uv] as:
```bash
uv run https://github.com/path/to/acnt-mgmt.py _action_ _arg_
```

Simply clone the repository to your local disk, `cd` into it, and use `uv run
acnt-mgmt.py` for all other actions.

## Optional Configuration

While you can pass the arguments on the command line, you can supply some as
environment variables. For the token, using [`direnv`][direnv] is recommended,
especially when combined with the 1Password [cli tool `op`][op]:

```bash
export OP_REFERENCE="op://whatever you need"
export HEROKU_TOKEN=$(op read "$OP_REFERENCE")
export HEROKU_TEAM=my_favorite_team
export HEROKU_USE_CLIPBOARD=True  # N.B. must be the exact string "True" to be true.
```

# Actions

## `list`

The `list` action examines all accounts, and looks for ones that do not match
our guidelines. See confluence for the currently allowed patterns, and actions
to take. List supports the option `--all` to include all the good ones as well,
along with their base permissions level.

## `emails`

The `emails` action simply outputs email addresses for all accounts. There is
no "group" that can be used to email all members.

## `verify`

The `verify` action just verifies if the supplied email is associated with a
Heroku account.

**N.B.** -- this does not need to be run before revoking an account -- the
code checks properly.

## `revoke`

The `revoke` action will revoke membership in the team for the supplied
account(s). The output is formatted to be pasted into an email to record the
action taken as needed.


[uv]: https://github.com/astral-sh/uv
[direnv]: https://direnv.net/
[op]: https://developer.1password.com/docs/cli/get-started/

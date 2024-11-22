#! /usr/bin/env -S uv run
# PYTHON_ARGCOMPLETE_OK
# /// script
# name = "Heroku-Account-Management"
# requires-python= ">=3.10"
# dependencies = [
#   "argcomplete>=3.5.1",
#   "pyperclip>=1.9.0",
# ]
# ///

import argparse
import dataclasses
import enum
import functools
import json
import os

# Functions to interact with Heroku API
import subprocess
from argparse import Namespace as Context
from urllib import request

import argcomplete
import pyperclip

# START embed support module for 1 file uv deployment
# we use a global for the token, in case it is referenced via a 1Password URL (we only want to auth/fetch once)
Heroku_Token = None


def login(token: str, team: str) -> None:
    """
    login Verify we have a token to use

    We don't actually test it's validity, but do retrieve it from a password store.

    Args:
        token (str): Actual API token, or keystore URL where it is stored. Currently, only 1Password is supported via it's CLI tool..
        team (str): Credentials are unique to 'teams' (aka accounts)

    Raises:
        SystemExit: A failure to retrieve a token means nothing else will work, so bail.
    """
    global Heroku_Token
    if Heroku_Token:
        # already done
        pass
    if token.startswith("op://"):
        # get credential from 1password cli tool
        try:
            job = subprocess.run(
                ["op", "read", f"{token}"], capture_output=True, check=True
            )
            token = job.stdout.strip().decode(encoding="utf-8")
        except Exception as e:
            raise SystemExit(f"failed to retrieve token from `op`: {repr(e)}")
    # TODO: test token validity
    Heroku_Token = token


@functools.lru_cache
def members(team: str) -> dict:
    """
    members return all members for this team

    Fetch all team members (JSON) and return as python dict for further processing. This is an "expensive" operation, so  cache results.

    TODO: consider disk cache, as there may be multiple CLI invocations
    TODO: verify that API call can not be paginated. This code assumes single response

    Args:
        team (str): Heroku team (aka account) to query

    Returns:
        dict: JSON response converted to Python dict. See XXX for details
    TODO: get URL reference for API call results
    """
    url = f"https://api.heroku.com/teams/{team}/members"
    headers = _get_headers()
    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req) as f:
        data = f.read().decode("utf-8")
    result = json.loads(data)
    return result


def _get_headers() -> dict[str:str]:
    """
    _get_headers DRY function to return HTTP headers used in all API calls



    Returns:
        dict: header name as key, header contents as value
    """
    headers = {
        "Accept": "application/vnd.heroku+json; version=3",
        "Authorization": f"Bearer {str(Heroku_Token)}",
    }

    return headers


def do_revoke(addr: str, ctx: Context) -> str:
    """
    revoke Revoke the supplied email and return  status

    Delete the account if it exists. We don't bother to check if the `addr` is valid to avoid race conditions.

    Args:
        addr (str): email address to revoke (although we treat as opaque string)
        ctx (Context): Used to extract `team` (account) to be used

    Returns:
        str: Test string suitable for being pasted into an offboarding email

    TODO: verify that custom access details are returned (as it was with bash scripts)
    """
    url = f"https://api.heroku.com/teams/{ctx.team}/members/{addr}"
    headers = _get_headers()
    req = request.Request(url, headers=headers, method="DELETE")
    result = ""
    try:
        with request.urlopen(req) as f:
            data = f.read().decode("utf-8")
            result = json.loads(data)
    except OSError as e:
        if e.code == 404:
            result = f"{addr} is not a member of {ctx.team} ({e.code})"
        else:
            raise

    return result


# END embed support module for 1 file uv deployment


# Account info we care about
class Account_Type(enum.Enum):
    """
    Account_Type How Mozilla classifies members and accounts
    """

    UNSET = enum.auto()
    STAFF = enum.auto()
    SERVICE = enum.auto()
    COMMUNITY = enum.auto()
    UNKNOWN = enum.auto()


class Account_Status(enum.Enum):
    """
    Account_Status Is the account following our rules
    """

    UNSET = enum.auto()
    OKAY = enum.auto()
    BAD = enum.auto()
    UNKNOWN = enum.auto()


# list from gcox on 2024-11-05
Staff_Email_Domains = (
    "@mozilla.com",
    "@mozillafoundation.org",
    "@getpocket.com",
    "@readitlater.com",
    "@mozilla-japan.org",
    "@mozilla.ai",
    "@mozilla.vc",
    "@thunderbird.net",
)


@dataclasses.dataclass()
class Account:
    """
    Focus on the account information we need for our functionality

    Heroku stores a lot more data in its account info than we need to reference. We extract the bits we care about into this record, and also store the values we compute from the Heroku data.

    Note that field names must match the dictionary keys in the dictionary returned from the `members` call.

    TODO: Be less hacky in how fields are initialized -- maybe the __init__ function should take the Heroku dictionary
    """

    email: str = ""  # the account identifier
    federated: bool = False  # is the account using SAML?
    role: str = str | None  # what is the account's assigned role
    two_factor_authentication: bool = (
        False  # does the account have 2FA enabled (will be False if using SAML)
    )
    account_type: Account_Type = (
        Account_Type.UNSET
    )  # what's the relationship of the account to Mozilla
    account_status: Account_Status = (
        Account_Status.UNSET
    )  # how does the account follow our rules
    needs_action: bool = True  # Is more investigation needed.

    def set_value(self, name: str, value: str) -> None:
        """
        set_value be able to access field as an attribute



        Args:
            name (str): field name
            value (str): field value
        """
        self.__setattr__(name, value)

    def classify(self) -> None:
        """
        classify Translate Heroku data into Mozilla's terms
        """
        assert self.account_type == Account_Type.UNSET
        assert self.account_status == Account_Status.UNSET

        # First figure out what type of account it is
        if self.email.endswith(Staff_Email_Domains):
            if self.email.startswith("heroku-"):  # marker for service account
                self.account_type = Account_Type.SERVICE
            else:
                self.account_type = Account_Type.STAFF
        else:
            if self.email.startswith("heroku-"):  # marker for service account
                # we don't expect community service accounts
                self.account_type = Account_Type.UNKNOWN
            else:
                self.account_type = Account_Type.COMMUNITY

        # Now figure if the authentication method is valid
        if self.federated and self.account_type == Account_Type.STAFF:
            self.account_status = Account_Status.OKAY
        elif (
            self.two_factor_authentication
            and self.account_type == Account_Type.COMMUNITY
        ):
            self.account_status = Account_Status.OKAY
        elif self.account_type == Account_Type.SERVICE and not (
            self.federated and self.two_factor_authentication
        ):
            self.account_status = Account_Status.OKAY
        elif self.account_status == Account_Status.UNKNOWN:
            self.account_status = Account_Status.UNKNOWN
        else:
            self.account_status = Account_Status.BAD

        # Finally, is action needed
        if (
            self.account_type not in (Account_Type.UNKNOWN, Account_Type.UNSET)
            and self.account_status is Account_Status.OKAY
        ):
            self.needs_action = False
        else:
            self.needs_action = True

        assert self.account_type != Account_Type.UNSET
        assert self.account_status != Account_Status.UNSET

    def as_text(self) -> str:
        """
        as_text -- translate the settings into understandable text

        _extended_summary_

        Returns:
            str: Something that's understandable to mere mortals
        """
        if self.needs_action:
            action = f"BAD! type={str(self.account_type.name)}; status={str(self.account_status.name)}; SSO={self.federated}; 2FA={self.two_factor_authentication}"
        else:
            action = "okay"

        text = f"{action}: {self.email} is a {self.account_type.name} account with {self.role} permissions."
        return text


# Heroku API access
def is_member(email: str, ctx: Context) -> bool:
    # hack for testing revoking
    if email.endswith("@example.com"):
        return True
    # real handling
    data = member_emails(ctx)
    result = email in data
    return result


def revoke(email: str, ctx: Context) -> list[str]:
    if not is_member(email, ctx):
        result = f"FAIL: {email} is not a member of {ctx.team}"
    else:
        result = do_revoke(email, ctx)
    return result


# Routines to report on members
def member_list(ctx: Context) -> list[Account]:
    everyone = all_members(ctx.team)
    result = []
    for acnt in everyone:
        if acnt.needs_action or ctx.all:
            result.append(acnt)
    return result


@functools.lru_cache
def all_members(team: str) -> list[Account]:
    data = members(team)
    result = []
    for d in data:
        acnt = Account()
        for k in (f.name for f in dataclasses.fields(Account)):
            if k in d:
                acnt.set_value(k, d[k])
        acnt.classify()
        result.append(acnt)
    return result


def member_emails(ctx: Context) -> list[str]:
    full_info = all_members(ctx.team)
    emails = [a.email for a in full_info]
    return emails


def membership_verify(ctx: Context) -> list[str]:
    status = []
    for addr in ctx.emails:
        if is_member(addr, ctx):
            status.append(f"{addr} is a member of {ctx.team}")
        else:
            status.append(f"{addr} is NOT a member of {ctx.team}")

    return status


def membership_revoke(ctx: Context) -> list[str]:
    status = []
    for addr in ctx.emails:
        if is_member(addr, ctx):
            try:
                status.append(revoke(addr, ctx))
            except Exception as e:
                print(repr(e))
                status.append(f"{addr} failed membership revocation from {ctx.team}")
        else:
            status.append(f"{addr} was NOT a member of {ctx.team}")

    return status


def _parse_args() -> argparse.Namespace:
    """
    _parse_args Handle CLI options and arguments

    Standard argparse with argcomplete

    Returns:
        argparse.Namespace: The namespace is also used as a global context object
    """
    parser = argparse.ArgumentParser()
    # Global Arguments
    parser.add_argument(
        "--token",
        default=os.getenv(
            "HEROKU_TOKEN",
            None,
        ),
        help="Heroku Auth Token or op url [env: HEROKU_TOKEN=]",
    )
    parser.add_argument(
        "--team",
        default=os.getenv("HEROKU_TEAM", "mozillacorporation"),
        help="Heroku team to query (default mozillacorporation) [env: HEROKU_TEAM=]",
    )
    use_clipboard = bool(os.getenv("HEROKU_USE_CLIPBOARD", "False") == "True")
    parser.add_argument(
        "--clip",
        action="store_true",
        default=use_clipboard,
        help=f"Place output on clipboard (default {use_clipboard}) [env: HEROKU_USE_CLIPBOARD=]",
    )
    parser.add_argument(
        "--no-clip",
        dest="clip",
        action="store_false",
        default=use_clipboard,
        help=f"Place output on clipboard (default {use_clipboard}) [env: HEROKU_USE_CLIPBOARD=]",
    )

    # sub commands
    subcommands = parser.add_subparsers(
        title="Supported Actions",
        description="various commands that can be performed (some may have options, check their --help)",
        required=True,
    )
    parser_list = subcommands.add_parser("list", help="list all problem members")
    parser_list.add_argument("--all", action="store_true", help="Show all members")
    parser_list.set_defaults(func=member_list)
    _ = subcommands.add_parser("emails", help="list all emails")
    _.set_defaults(func=member_emails)
    parser_verify = subcommands.add_parser(
        "verify", help="verify membership of supplied emails"
    )
    parser_verify.add_argument("emails", nargs="+")
    parser_verify.set_defaults(func=membership_verify)
    parser_revoke = subcommands.add_parser(
        "revoke", help="revoke membership of supplied emails"
    )
    parser_revoke.add_argument("emails", nargs="+")
    parser_revoke.set_defaults(func=membership_revoke)

    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    return args


def main() -> None:
    context = _parse_args()

    login(context.token, context.team)
    result = context.func(context)
    fname = context.func.__name__.split("_")[1]
    print(f"result of running {fname}")
    if isinstance(result[0], Account):
        output = "\n".join(r.as_text() for r in result)
    else:
        output = "\n".join(result)
    if context.clip:
        pyperclip.copy(output)
        print("(also copied to clipboard)")
    print(output)


if __name__ == "__main__":
    main()

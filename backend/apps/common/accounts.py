from rest_framework.exceptions import NotFound, ParseError

from .models import BrokerAccount


def account_code_from_request(request):
    value = request.query_params.get("account")
    if value in (None, "") and request.method not in ("GET", "HEAD", "OPTIONS"):
        value = request.data.get("account")
    return str(value or "").strip()


def resolve_request_account(request, *, allow_all=False):
    """Resolve an exact account boundary for an API request.

    Single-account installations remain backward compatible. As soon as more than
    one active account exists, account-scoped endpoints require an explicit code.
    """
    code = account_code_from_request(request)
    if code:
        account = BrokerAccount.objects.filter(
            broker="ibkr",
            account_code=code,
            is_active=True,
        ).first()
        if not account:
            raise NotFound(f"Unknown or inactive account: {code}")
        return account

    if allow_all:
        return None

    active_accounts = list(BrokerAccount.objects.filter(is_active=True)[:2])
    if len(active_accounts) == 1:
        return active_accounts[0]
    if not active_accounts:
        raise ParseError("No active broker account is available. Run a sync first.")
    raise ParseError("The account query parameter is required when multiple accounts are active.")

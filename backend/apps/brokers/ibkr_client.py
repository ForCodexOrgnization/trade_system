import time
from pathlib import Path
from decimal import Decimal
from datetime import date, datetime, timedelta
import xml.etree.ElementTree as ET

import requests
from django.conf import settings
from django.utils import timezone


class IBKRClient:
    # These codes describe reports that are temporarily unavailable or are still
    # being generated. Treating 1004/1019 as hard failures makes a large report
    # look incomplete even though IBKR explicitly asks the client to retry.
    RETRYABLE_ERROR_CODES = {
        "1001", "1003", "1004", "1005", "1006", "1007", "1008", "1009",
        "1018", "1019", "1021",
    }
    MAX_FLEX_RANGE_DAYS = 365

    def __init__(self, use_local_flex_xml: bool = False):
        self.use_local_flex_xml = use_local_flex_xml
        self.last_fetch_metadata: dict = {}

    @property
    def flex_statement_cache_path(self) -> Path:
        return Path(settings.BASE_DIR) / "data" / "ibkr_last_flex_statement.xml"

    @property
    def has_flex_statement_cache(self) -> bool:
        return self.flex_statement_cache_path.exists()

    def fetch_all_executions(self) -> list[dict]:
        if self.use_local_flex_xml:
            xml_text = self.fetch_local_flex_statement_xml()
            rows = self.parse_flex_xml(xml_text)
            self.last_fetch_metadata = self._build_fetch_metadata(rows, [], source="local_cache")
            return rows

        ranges = self.full_history_ranges()
        if ranges is None:
            # The saved Flex Query owns its reporting period. This is the safest
            # default because IBKR counts unavailable date overrides as failed
            # requests and can block the token after only a few such attempts.
            xml_text = self.fetch_flex_statement_xml()
            self.cache_flex_statement_xml(xml_text)
            rows = self.parse_flex_xml(xml_text)
            self.last_fetch_metadata = self._build_fetch_metadata(
                rows,
                [{"from_date": None, "to_date": None, "raw_count": len(rows)}],
                source="ibkr_query_period",
            )
            return rows

        documents: list[str] = []
        rows: list[dict] = []
        chunk_metadata = []
        seen_execution_keys = set()

        for range_index, (from_date, to_date) in enumerate(ranges):
            xml_text = self.fetch_flex_statement_xml(from_date=from_date, to_date=to_date)
            documents.append(xml_text)
            chunk_rows = self.parse_flex_xml(xml_text)
            chunk_metadata.append({
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "raw_count": len(chunk_rows),
            })
            for row in chunk_rows:
                # Date ranges are inclusive. This also protects against an IBKR
                # report unexpectedly repeating executions between statements.
                key = (
                    row.get("account"),
                    row.get("execution_id"),
                    row.get("extra_trade_id"),
                )
                if key in seen_execution_keys:
                    continue
                seen_execution_keys.add(key)
                rows.append(row)
            if range_index < len(ranges) - 1:
                # /SendRequest is paced at one request per second per token.
                time.sleep(1)

        self.cache_flex_statement_xml(self.combine_flex_documents(documents))
        self.last_fetch_metadata = self._build_fetch_metadata(rows, chunk_metadata, source="ibkr")
        return rows

    def full_history_ranges(self, today: date | None = None) -> list[tuple[date, date]] | None:
        """Return optional date overrides split into inclusive <=365-day requests."""
        today = today or timezone.localdate()
        configured_history_years = getattr(settings, "IBKR_FLEX_HISTORY_YEARS", None)
        if configured_history_years is None:
            return None
        history_years = max(0, int(configured_history_years))
        cursor = date(today.year - history_years, 1, 1)
        ranges = []
        while cursor <= today:
            chunk_end = min(cursor + timedelta(days=self.MAX_FLEX_RANGE_DAYS - 1), today)
            ranges.append((cursor, chunk_end))
            cursor = chunk_end + timedelta(days=1)
        return ranges

    def combine_flex_documents(self, documents: list[str]) -> str:
        """Create one valid cache document that the existing local sync can parse."""
        root = ET.Element("FlexQueryResponses")
        for xml_text in documents:
            try:
                root.append(ET.fromstring(xml_text))
            except ET.ParseError as exc:
                raise ValueError(f"Invalid XML from IBKR Flex statement: {exc}") from exc
        return ET.tostring(root, encoding="unicode")

    def _build_fetch_metadata(self, rows: list[dict], chunks: list[dict], source: str) -> dict:
        executed_dates = sorted(
            row["executed_at"].date() for row in rows if row.get("executed_at")
        )
        return {
            "source": source,
            "chunk_count": len(chunks),
            "chunks": chunks,
            "execution_count": len(rows),
            "earliest_execution_date": executed_dates[0].isoformat() if executed_dates else None,
            "latest_execution_date": executed_dates[-1].isoformat() if executed_dates else None,
        }

    def fetch_local_flex_statement_xml(self) -> str:
        path = self.flex_statement_cache_path
        if not path.exists():
            raise FileNotFoundError(
                f"Local IBKR Flex XML cache not found at {path}. "
                "Run a real IBKR sync once before using local sync."
            )
        return path.read_text(encoding="utf-8")

    def cache_flex_statement_xml(self, xml_text: str) -> None:
        path = self.flex_statement_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml_text, encoding="utf-8")

    def fetch_flex_statement_xml(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> str:
        token = settings.IBKR_FLEX_TOKEN
        query_id = settings.IBKR_FLEX_QUERY_ID

        if not token or not query_id:
            raise ValueError(
                "IBKR_FLEX_TOKEN or IBKR_FLEX_QUERY_ID is missing. "
                "Please set them in backend/.env or your run configuration."
            )

        last_send_xml = ""
        # Re-submitting an invalid query too aggressively causes IBKR to block
        # the token with ErrorCode 1025. Keep retries deliberately small; once
        # SendRequest succeeds, GetStatement polling uses the same reference and
        # does not create another report request.
        max_send_attempts = 3
        send_params = {"t": token, "q": query_id, "v": "3"}
        if from_date and to_date:
            send_params.update({
                "fd": from_date.strftime("%Y%m%d"),
                "td": to_date.strftime("%Y%m%d"),
            })
        headers = {"User-Agent": getattr(settings, "IBKR_FLEX_USER_AGENT", "IBKRTradeJournal/1.0")}
        for send_attempt in range(max_send_attempts):
            send_resp = requests.get(
                settings.IBKR_FLEX_SEND_REQUEST_URL,
                params=send_params,
                headers=headers,
                timeout=60,
            )
            send_resp.raise_for_status()
            last_send_xml = send_resp.text

            reference_code = self.parse_reference_code(last_send_xml)
            if reference_code:
                wait_seconds = 0
                max_wait_seconds = 180
                poll_interval_seconds = 3
                while wait_seconds < max_wait_seconds:
                    get_resp = requests.get(
                        settings.IBKR_FLEX_GET_STATEMENT_URL,
                        params={"t": token, "q": reference_code, "v": "3"},
                        headers=headers,
                        timeout=60,
                    )
                    get_resp.raise_for_status()

                    xml_text = get_resp.text
                    if self._is_flex_statement_ready(xml_text):
                        return xml_text

                    error_code, _ = self.parse_send_request_error(xml_text)
                    if error_code and error_code not in self.RETRYABLE_ERROR_CODES:
                        raise RuntimeError(f"IBKR Flex get-statement failed with ErrorCode {error_code}.")

                    time.sleep(poll_interval_seconds)
                    wait_seconds += poll_interval_seconds

                raise TimeoutError("Timed out waiting for Flex statement after 180 seconds.")

            error_code, error_message = self.parse_send_request_error(last_send_xml)
            if error_code == "1003" and from_date and to_date:
                # IBKR returns "Statement is not available" for explicit date
                # ranges before an account existed (or otherwise has no
                # available statement). That is an empty history chunk, not a
                # reason to abort later chunks that may contain executions.
                return (
                    '<FlexQueryResponse><FlexStatements count="0" />'
                    '</FlexQueryResponse>'
                )
            if error_code in self.RETRYABLE_ERROR_CODES and send_attempt < max_send_attempts - 1:
                # 1018 is a per-token one-minute pacing window. Other temporary
                # generation failures get a shorter, still conservative backoff.
                time.sleep(60 if error_code == "1018" else 15)
                continue

            if error_code in self.RETRYABLE_ERROR_CODES:
                raise RuntimeError(
                    f"IBKR Flex report is temporarily unavailable (ErrorCode {error_code}). "
                    "Please wait a few minutes and try again."
                )

            if error_code:
                detail = f" ({error_message})" if error_message else ""
                if error_code == "1025":
                    raise RuntimeError(
                        "IBKR Flex Web Service is rejecting requests after too many failed attempts "
                        "(ErrorCode 1025). This is an account/service-level state and can persist even "
                        "with the newest token. Stop retrying, then disable and re-enable Flex Web "
                        "Service in Client Portal (or wait for IBKR's lockout to expire), confirm its "
                        "status is Active, and try once more."
                    )
                raise RuntimeError(f"IBKR Flex send-request failed with ErrorCode {error_code}{detail}.")

            raise ValueError(f"Could not get Flex reference code: {last_send_xml}")

        raise RuntimeError(
            "IBKR Flex report is temporarily unavailable (ErrorCode 1001). "
            "Please wait a few minutes and try again."
        )

    def _is_flex_statement_ready(self, xml_text: str) -> bool:
        # A valid Flex response may contain zero trades for the query window,
        # so we should treat a FlexStatement payload as "ready" even when the
        # <Trades> section is absent. Do not use a string prefix check here:
        # IBKR errors use <FlexStatementResponse>, which previously matched
        # "<FlexStatement" and was silently parsed as an empty report.
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return False
        return any(element.tag.rsplit("}", 1)[-1] == "FlexStatement" for element in root.iter())

    def parse_send_request_error(self, xml_text: str) -> tuple[str | None, str | None]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None, None

        code = root.findtext(".//ErrorCode")
        message = root.findtext(".//ErrorMessage")
        return code, message

    def parse_reference_code(self, xml_text: str) -> str | None:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid XML from IBKR Flex send request: {exc}") from exc
        elem = root.find(".//ReferenceCode")
        return elem.text if elem is not None else None

    def parse_flex_xml(self, xml_text: str) -> list[dict]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid XML from IBKR Flex statement: {exc}") from exc
        rows: list[dict] = []

        for trade in root.findall(".//Trades/Trade"):
            data = trade.attrib
            row = self.map_trade_node(data)
            rows.append(row)

        return rows

    def map_trade_node(self, data: dict) -> dict:
        side_raw = (data.get("buySell") or "").upper().strip()
        if side_raw not in {"BUY", "SELL", "BOT", "SLD"}:
            raise ValueError(f"Unexpected buySell value: {side_raw}")

        side = "BUY" if side_raw in {"BUY", "BOT"} else "SELL"

        qty = self.to_decimal(data.get("quantity", "0"))
        qty_abs = abs(qty)

        return {
            "execution_id": data.get("ibExecID") or data.get("tradeID"),
            "perm_id": data.get("ibOrderID") or data.get("orderReference"),
            "order_id": data.get("ibOrderID"),
            "client_id": None,
            "account": data.get("accountId"),
            "symbol": data.get("symbol"),
            "local_symbol": data.get("description") or data.get("underlyingSymbol"),
            "conid": data.get("conid"),
            "sec_type": data.get("assetCategory"),
            "currency": data.get("currency"),
            "exchange": data.get("exchange") or data.get("listingExchange"),
            "side": side,
            "quantity": qty_abs,
            "price": self.to_decimal(data.get("tradePrice", "0")),
            "commission": abs(self.to_decimal(data.get("ibCommission", "0"))),
            "realized_pnl": self.to_decimal(data.get("fifoPnlRealized", "0")),
            "executed_at": self.parse_ibkr_datetime(data.get("dateTime")),
            "extra_open_close": data.get("openCloseIndicator"),
            "extra_multiplier": self.to_decimal(data.get("multiplier", "1")),
            "extra_trade_id": data.get("tradeID"),
            "extra_order_type": data.get("orderType"),
            "extra_proceeds": self.to_decimal(data.get("proceeds", "0")),
            "extra_net_cash": self.to_decimal(data.get("netCash", "0")),
            "raw_payload": data,
        }

    def parse_ibkr_datetime(self, value: str) -> datetime:
        if not value:
            raise ValueError("Missing dateTime in Flex XML.")
        parsed = datetime.strptime(value, "%Y%m%d;%H%M%S")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def to_decimal(self, value) -> Decimal:
        if value in [None, ""]:
            return Decimal("0")
        return Decimal(str(value).replace(",", ""))

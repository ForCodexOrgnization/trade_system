import time
from pathlib import Path
from decimal import Decimal
from datetime import datetime
import xml.etree.ElementTree as ET

import requests
from django.conf import settings
from django.utils import timezone


class IBKRClient:
    SEND_RETRYABLE_ERROR_CODES = {"1001"}

    def __init__(self, use_local_flex_xml: bool = False):
        self.use_local_flex_xml = use_local_flex_xml

    @property
    def flex_statement_cache_path(self) -> Path:
        return Path(settings.BASE_DIR) / "data" / "ibkr_last_flex_statement.xml"

    @property
    def has_flex_statement_cache(self) -> bool:
        return self.flex_statement_cache_path.exists()

    def fetch_all_executions(self) -> list[dict]:
        if self.use_local_flex_xml:
            xml_text = self.fetch_local_flex_statement_xml()
        else:
            xml_text = self.fetch_flex_statement_xml()
            self.cache_flex_statement_xml(xml_text)
        return self.parse_flex_xml(xml_text)

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

    def fetch_flex_statement_xml(self) -> str:
        token = settings.IBKR_FLEX_TOKEN
        query_id = settings.IBKR_FLEX_QUERY_ID

        if not token or not query_id:
            raise ValueError(
                "IBKR_FLEX_TOKEN or IBKR_FLEX_QUERY_ID is missing. "
                "Please set them in backend/.env or your run configuration."
            )

        last_send_xml = ""
        max_send_attempts = 20
        for send_attempt in range(max_send_attempts):
            send_resp = requests.get(
                settings.IBKR_FLEX_SEND_REQUEST_URL,
                params={"t": token, "q": query_id, "v": "3"},
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
                        timeout=60,
                    )
                    get_resp.raise_for_status()

                    xml_text = get_resp.text
                    if self._is_flex_statement_ready(xml_text):
                        return xml_text

                    error_code, _ = self.parse_send_request_error(xml_text)
                    if error_code and error_code not in self.SEND_RETRYABLE_ERROR_CODES:
                        raise RuntimeError(f"IBKR Flex get-statement failed with ErrorCode {error_code}.")

                    time.sleep(poll_interval_seconds)
                    wait_seconds += poll_interval_seconds

                raise TimeoutError("Timed out waiting for Flex statement after 180 seconds.")

            error_code, error_message = self.parse_send_request_error(last_send_xml)
            if error_code in self.SEND_RETRYABLE_ERROR_CODES and send_attempt < max_send_attempts - 1:
                time.sleep(3)
                continue

            if error_code in self.SEND_RETRYABLE_ERROR_CODES:
                raise RuntimeError(
                    "IBKR Flex report is temporarily unavailable (ErrorCode 1001). "
                    "Please wait a few minutes and try again."
                )

            if error_code:
                detail = f" ({error_message})" if error_message else ""
                raise RuntimeError(f"IBKR Flex send-request failed with ErrorCode {error_code}{detail}.")

            raise ValueError(f"Could not get Flex reference code: {last_send_xml}")

        raise RuntimeError(
            "IBKR Flex report is temporarily unavailable (ErrorCode 1001). "
            "Please wait a few minutes and try again."
        )

    def _is_flex_statement_ready(self, xml_text: str) -> bool:
        # A valid Flex response may contain zero trades for the query window,
        # so we should treat a FlexStatement payload as "ready" even when the
        # <Trades> section is absent.
        return "<FlexStatement" in xml_text

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

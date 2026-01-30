import uuid
import logging
import asyncio
from typing import Optional, Dict, Any, List

from yookassa import Configuration, Payment as YooKassaPayment
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder
from yookassa.domain.common.confirmation_type import ConfirmationType
from yookassa.domain.notification import WebhookNotificationFactory

from ..config import settings


class YooKassaService:
    """
    Service for interacting with the YooKassa API for creating and checking payments.
    Configures the YooKassa SDK using settings from config.py.
    """

    def __init__(self, bot_username: Optional[str] = None):
        # Configure SDK with credentials from settings
        Configuration.account_id = settings.YOOKASSA_SHOP_ID.get_secret_value() if settings.YOOKASSA_SHOP_ID else None
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY.get_secret_value() if settings.YOOKASSA_SECRET_KEY else None

        # Set webhook URL for receiving notifications
        if settings.YOOKASSA_NOTIFICATION_URL:
            Configuration.webhook_url = settings.YOOKASSA_NOTIFICATION_URL
            logging.info(f"YooKassa SDK webhook_url set to: {settings.YOOKASSA_NOTIFICATION_URL}")
        else:
            logging.warning("YOOKASSA_NOTIFICATION_URL is not set in settings. YooKassa webhooks will not be configured.")

        # Check if YooKassa is enabled and configured
        if not settings.YOOKASSA_ENABLED:
            logging.warning("YooKassa is disabled via YOOKASSA_ENABLED flag. Payment functionality will be DISABLED.")
            self.configured = False
        elif not Configuration.account_id or not Configuration.secret_key:
            logging.warning(
                "YooKassa SHOP_ID or SECRET_KEY not configured in settings. "
                "Payment functionality will be DISABLED.")
            self.configured = False
        else:
            self.configured = True
            logging.info(
                f"YooKassa SDK configured for shop_id: {Configuration.account_id[:5]}..."
            )

        # Determine return URL for user redirection after payment
        if settings.YOOKASSA_RETURN_URL:
            self.return_url = settings.YOOKASSA_RETURN_URL
        elif bot_username:
            self.return_url = f"https://t.me/{bot_username}"
            logging.info(f"YOOKASSA_RETURN_URL not set, using dynamic default based on bot username: {self.return_url}")
        else:
            self.return_url = "https://example.com/payment_error_no_return_url_configured"
            logging.warning(
                f"CRITICAL: YOOKASSA_RETURN_URL not set AND bot username not provided. "
                f"Using placeholder: {self.return_url}. Payments may not complete correctly."
            )
        logging.info(f"YooKassa Service effective return_url for payments: {self.return_url}")

    async def create_payment(
            self,
            amount: float,
            currency: str,
            description: str,
            metadata: Dict[str, Any],
            receipt_email: Optional[str] = None,
            receipt_phone: Optional[str] = None,
            save_payment_method: bool = False,
            payment_method_id: Optional[str] = None,
            capture: bool = True,
            bind_only: bool = False) -> Optional[Dict[str, Any]]:
        if not self.configured:
            logging.error("YooKassa is not configured. Cannot create payment.")
            return None

        customer_contact_for_receipt = {}
        if receipt_email:
            customer_contact_for_receipt["email"] = receipt_email
        elif receipt_phone:
            customer_contact_for_receipt["phone"] = receipt_phone
        elif settings.YOOKASSA_DEFAULT_RECEIPT_EMAIL:
            customer_contact_for_receipt["email"] = settings.YOOKASSA_DEFAULT_RECEIPT_EMAIL
        else:
            logging.error("CRITICAL: No email/phone for YooKassa receipt provided and YOOKASSA_DEFAULT_RECEIPT_EMAIL is not set.")
            return {"error": True, "internal_message": "YooKassa receipt customer contact (email/phone) missing and no default email configured."}

        try:
            builder = PaymentRequestBuilder()
            builder.set_amount({
                "value": str(round(amount, 2)),
                "currency": currency.upper()
            })
            if bind_only:
                capture = False
                amount = max(amount, 1.00)
            builder.set_capture(capture)
            if not payment_method_id:
                builder.set_confirmation({"type": ConfirmationType.REDIRECT, "return_url": self.return_url})
            builder.set_description(description)
            builder.set_metadata(metadata)
            if save_payment_method:
                builder.set_save_payment_method(True)
            if payment_method_id:
                builder.set_payment_method_id(payment_method_id)

            receipt_items_list: List[Dict[str, Any]] = [{
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": str(round(amount, 2)), "currency": currency.upper()},
                "vat_code": str(settings.YOOKASSA_VAT_CODE),
                "payment_mode": getattr(settings, 'yk_receipt_payment_mode', settings.YOOKASSA_PAYMENT_MODE),
                "payment_subject": getattr(settings, 'yk_receipt_payment_subject', settings.YOOKASSA_PAYMENT_SUBJECT)
            }]

            receipt_data_dict: Dict[str, Any] = {"customer": customer_contact_for_receipt, "items": receipt_items_list}
            builder.set_receipt(receipt_data_dict)

            idempotence_key = str(uuid.uuid4())
            payment_request = builder.build()

            logging.info(f"Creating YooKassa payment (Idempotence-Key: {idempotence_key}). Amount: {amount} {currency}. Metadata: {metadata}. Receipt: {receipt_data_dict}")

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: YooKassaPayment.create(payment_request, idempotence_key))

            logging.info(f"YooKassa Payment.create response: ID={response.id}, Status={response.status}, Paid={response.paid}")

            return {
                "id": response.id,
                "confirmation_url": response.confirmation.confirmation_url if response.confirmation else None,
                "status": response.status,
                "metadata": response.metadata,
                "amount_value": float(response.amount.value),
                "amount_currency": response.amount.currency,
                "idempotence_key_used": idempotence_key,
                "paid": response.paid,
                "refundable": response.refundable,
                "created_at": response.created_at.isoformat() if hasattr(response.created_at, 'isoformat') else str(response.created_at),
                "description_from_yk": response.description,
                "test_mode": response.test if hasattr(response, 'test') else None,
                "payment_method": getattr(response, 'payment_method', None),
            }
        except Exception as e:
            logging.error(f"YooKassa payment creation failed: {e}", exc_info=True)
            return None

    async def get_payment_info(self, payment_id_in_yookassa: str) -> Optional[Dict[str, Any]]:
        if not self.configured:
            logging.error("YooKassa is not configured. Cannot get payment info.")
            return None
        try:
            logging.info(f"Fetching payment info from YooKassa for ID: {payment_id_in_yookassa}")

            loop = asyncio.get_running_loop()
            payment_info_yk = await loop.run_in_executor(None, lambda: YooKassaPayment.find_one(payment_id_in_yookassa))

            if payment_info_yk:
                logging.info(f"YooKassa payment info for {payment_id_in_yookassa}: Status={payment_info_yk.status}, Paid={payment_info_yk.paid}")
                pm = getattr(payment_info_yk, 'payment_method', None)
                pm_payload: Dict[str, Any] = {}
                if pm:
                    pm_id = getattr(pm, 'id', None)
                    pm_type = getattr(pm, 'type', None)
                    pm_title = getattr(pm, 'title', None)
                    account_number = getattr(pm, 'account_number', None) or getattr(pm, 'account', None)
                    card_obj = getattr(pm, 'card', None)
                    last4_val = None
                    if card_obj and hasattr(card_obj, 'last4'):
                        last4_val = getattr(card_obj, 'last4')
                    elif isinstance(account_number, str) and len(account_number) >= 4:
                        last4_val = account_number[-4:]
                    pm_payload = {
                        "id": pm_id, "type": pm_type, "title": pm_title, "card_last4": last4_val,
                    }
                return {
                    "id": payment_info_yk.id, "status": payment_info_yk.status, "paid": payment_info_yk.paid,
                    "amount_value": float(payment_info_yk.amount.value), "amount_currency": payment_info_yk.amount.currency,
                    "metadata": payment_info_yk.metadata, "description": payment_info_yk.description,
                    "refundable": payment_info_yk.refundable,
                    "created_at": payment_info_yk.created_at.isoformat() if hasattr(payment_info_yk.created_at, 'isoformat') else str(payment_info_yk.created_at),
                    "captured_at": payment_info_yk.captured_at.isoformat() if getattr(payment_info_yk, 'captured_at', None) and hasattr(payment_info_yk.captured_at, 'isoformat') else None,
                    "payment_method": pm_payload, "test_mode": getattr(payment_info_yk, 'test', None),
                }
            else:
                logging.warning(f"No payment info found in YooKassa for ID: {payment_id_in_yookassa}")
                return None
        except Exception as e:
            logging.error(f"YooKassa get payment info for {payment_id_in_yookassa} failed: {e}", exc_info=True)
            return None

    async def cancel_payment(self, payment_id_in_yookassa: str) -> bool:
        if not self.configured:
            logging.error("YooKassa is not configured. Cannot cancel payment.")
            return False
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: YooKassaPayment.cancel(payment_id_in_yookassa))
            logging.info(f"Cancelled YooKassa payment {payment_id_in_yookassa}")
            return True
        except Exception as e:
            logging.error(f"Failed to cancel YooKassa payment {payment_id_in_yookassa}: {e}")
            return False
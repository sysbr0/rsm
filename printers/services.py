
# Create your tests here.
from collections import defaultdict
import socket

from django.db import transaction
from django.utils import timezone

from orders.models import Order, OrderItem
from printers.models import (
    MessageToPrinter,
    PrintJob,
    PrintJobStatus,
    Printer,
)

#from printers.templates import build_order_item_ticket


# ============================================================
# ESC/POS PRINTER
# ============================================================

class ESCPosPrinter:
    """
    Simple TCP/IP ESC/POS printer client.

    Works with:
    - CrossEscPos
    - XPrinter
    - Epson
    - Rongta
    - Other network ESC/POS printers
    """

    def __init__(
        self,
        host: str,
        port: int = 9100,
        timeout: int = 5,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, data: bytes):
        """
        Send ESC/POS data to the printer.
        """

        with socket.create_connection(
            (self.host, self.port),
            timeout=self.timeout,
        ) as connection:
            connection.sendall(data)

    def test(self):
        """
        Send a simple test receipt.
        """

        data = b""

        # Initialize printer
        data += b"\x1b\x40"

        # Center alignment
        data += b"\x1b\x61\x01"

        # Bold ON
        data += b"\x1b\x45\x01"

        data += b"RESTAURANT TEST\n"

        # Bold OFF
        data += b"\x1b\x45\x00"

        data += b"\n"
        data += b"Printer connection OK\n"
        data += b"\n\n\n"

        self.send(data)


# ============================================================
# TEXT → ESC/POS
# ============================================================

def text_to_escpos(content: str) -> bytes:
    """
    Convert normal receipt text into ESC/POS data.
    """

    data = b""

    # Initialize
    data += b"\x1b\x40"

    # Left alignment
    data += b"\x1b\x61\x00"

    # Receipt text
    data += content.encode(
        "utf-8",
        errors="replace",
    )

    # Feed paper
    data += b"\n\n\n"

    return data


# ============================================================
# CREATE PRINT JOBS
# ============================================================

def enqueue_print_jobs_for_order(
    order: Order,
) -> list[PrintJob]:

    pending_items = list(
        OrderItem.objects
        .select_related(
            "product",
            "product__section",
        )
        .filter(
            order=order,
            has_print_job=False,
        )
        .order_by("id")
    )

    if not pending_items:
        return []

    grouped = defaultdict(list)

    for item in pending_items:
        grouped[item.product.section_id].append(item)

    jobs: list[PrintJob] = []

    with transaction.atomic():

        for section_id, items in grouped.items():

            printer = (
                Printer.objects
                .filter(
                    section_id=section_id,
                    is_active=True,
                )
                .select_related("section")
                .first()
            )

            # No printer configured for this section
            if not printer:
                continue

            content = build_order_item_ticket(
                order=order,
                section=printer.section,
                items=items,
            )

            job = PrintJob.objects.create(
                order_id=order.id,
                section_id=section_id,
                printer=printer,
                status=PrintJobStatus.PENDING,
                content=content,
            )

            jobs.append(job)

        # Mark items as having a print job
        for item in pending_items:

            item.has_print_job = True

            item.save(
                update_fields=[
                    "has_print_job",
                    "updated_at",
                ]
            )

    return jobs


# ============================================================
# PROCESS ONE PRINT JOB
# ============================================================

def process_print_job(job: PrintJob) -> PrintJob:
    """
    Immediately send one PrintJob to its printer.

    Flow:

    PENDING
        ↓
    PRINTING
        ↓
    PRINTED

    If something fails:

    PRINTING
        ↓
    FAILED
    """

    # --------------------------------------------------------
    # Mark job as PRINTING
    # --------------------------------------------------------

    job.status = PrintJobStatus.PRINTING
    job.error_message = ""

    job.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
    )

    # --------------------------------------------------------
    # Send to printer
    # --------------------------------------------------------

    try:

        printer = job.printer

        # Printer must be active
        if not printer.is_active:
            raise ValueError(
                f"Printer '{printer.name}' is inactive."
            )

        # Currently support network printers
        if printer.connection_type != "NETWORK":
            raise ValueError(
                f"Printer '{printer.name}' "
                f"is not a network printer."
            )

        # Printer must have an IP
        if not printer.ip_address:
            raise ValueError(
                f"Printer '{printer.name}' "
                f"does not have an IP address."
            )

        # ----------------------------------------------------
        # Create printer connection
        # ----------------------------------------------------

        device = ESCPosPrinter(
            host=printer.ip_address,
            port=printer.port or 9100,
        )

        # ----------------------------------------------------
        # Convert content to ESC/POS
        # ----------------------------------------------------

        receipt_data = text_to_escpos(
            job.content
        )

        # ----------------------------------------------------
        # SEND TO PRINTER
        # ----------------------------------------------------

        device.send(receipt_data)

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        job.status = PrintJobStatus.PRINTED
        job.printed_at = timezone.now()
        job.error_message = ""

        job.save(
            update_fields=[
                "status",
                "printed_at",
                "error_message",
                "updated_at",
            ]
        )

    except Exception as exc:

        # ----------------------------------------------------
        # FAILURE
        # ----------------------------------------------------

        job.status = PrintJobStatus.FAILED
        job.retry_count += 1
        job.error_message = str(exc)[:255]

        job.save(
            update_fields=[
                "status",
                "retry_count",
                "error_message",
                "updated_at",
            ]
        )

    return job


# ============================================================
# TEST A PRINTER
# ============================================================

def test_printer(printer: Printer):

    if not printer.is_active:
        raise ValueError(
            f"Printer '{printer.name}' is inactive."
        )

    if printer.connection_type != "NETWORK":
        raise ValueError(
            "Only NETWORK printers are supported "
            "by the current test."
        )

    if not printer.ip_address:
        raise ValueError(
            f"Printer '{printer.name}' "
            f"has no IP address."
        )

    device = ESCPosPrinter(
        host=printer.ip_address,
        port=printer.port or 9100,
    )

    device.test()


# ============================================================
# MESSAGE TO PRINTER
# ============================================================

def build_message_ticket(
    message: MessageToPrinter,
    width: int = 42,
) -> str:
    """
    Build the printable ticket for a waiter message.
    """

    table = message.table
    waiter = message.waiter
    now = timezone.localtime()

    lines = []

    def separator(char="-"):
        return char * width

    def centered(text):
        return str(text).center(width)

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    lines.append(centered("RESTAURANT"))
    lines.append(separator("="))

    # --------------------------------------------------------
    # TABLE
    # --------------------------------------------------------

    lines.append(
        f"TABLE   : {table.name}"
    )

    lines.append(
        f"TABLE # : {table.table_number}"
    )

    # --------------------------------------------------------
    # WAITER
    # --------------------------------------------------------

    if waiter:

        waiter_name = (
            getattr(waiter, "full_name", None)
            or getattr(waiter, "username", None)
            or str(waiter)
        )

        lines.append(
            f"WAITER  : {waiter_name}"
        )

    else:

        lines.append(
            "WAITER  : -"
        )

    # --------------------------------------------------------
    # DATE / TIME
    # --------------------------------------------------------

    lines.append(
        f"DATE    : {now.strftime('%Y-%m-%d')}"
    )

    lines.append(
        f"TIME    : {now.strftime('%H:%M:%S')}"
    )

    # --------------------------------------------------------
    # PRINTER
    # --------------------------------------------------------

    lines.append(
        f"PRINTER : {message.printer.name}"
    )

    lines.append(separator("="))

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    lines.append(
        centered("MESSAGE")
    )

    lines.append(separator("-"))

    for line in str(message.message).splitlines():
        lines.append(line)

    lines.append(separator("-"))

    lines.append(
        centered("PLEASE ATTEND")
    )

    lines.append("")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# DIRECT MESSAGE PRINTING
# ============================================================

def print_message_to_printer(
    message: MessageToPrinter,
) -> PrintJob:
    """
    Directly print a MessageToPrinter to the printer
    selected by the waiter.

    IMPORTANT:

    This function does NOT create a PENDING PrintJob
    and does NOT call process_print_job().

    The message is sent directly to the selected printer.

    A PrintJob is created only AFTER successful printing
    as a historical record.
    """

    printer = message.printer

    # --------------------------------------------------------
    # Validate printer
    # --------------------------------------------------------

    if not printer:
        raise ValueError(
            "No printer selected for this message."
        )

    if not printer.is_active:
        raise ValueError(
            f"Printer '{printer.name}' is inactive."
        )

    if printer.connection_type != "NETWORK":
        raise ValueError(
            f"Printer '{printer.name}' "
            f"is not a network printer."
        )

    if not printer.ip_address:
        raise ValueError(
            f"Printer '{printer.name}' "
            f"does not have an IP address."
        )

    # --------------------------------------------------------
    # Build message ticket
    # --------------------------------------------------------

    content = build_message_ticket(
        message
    )

    try:

        # ----------------------------------------------------
        # DIRECT PRINT
        # ----------------------------------------------------

        device = ESCPosPrinter(
            host=printer.ip_address,
            port=printer.port or 9100,
        )

        receipt_data = text_to_escpos(
            content
        )

        device.send(
            receipt_data
        )

    except Exception as exc:

        # ----------------------------------------------------
        # PRINT FAILED
        # ----------------------------------------------------

        message.is_printed = False

        message.error_message = str(exc)[:255]

        message.save(
            update_fields=[
                "is_printed",
                "error_message",
                "updated_at",
            ]
        )

        raise

    # --------------------------------------------------------
    # PRINT SUCCESS
    # --------------------------------------------------------

    printed_at = timezone.now()

    message.is_printed = True
    message.printed_at = printed_at
    message.error_message = ""

    message.save(
        update_fields=[
            "is_printed",
            "printed_at",
            "error_message",
            "updated_at",
        ]
    )

    # --------------------------------------------------------
    # CREATE HISTORY RECORD
    # --------------------------------------------------------

    job = PrintJob.objects.create(
        order_id=None,
        section=printer.section,
        printer=printer,
        status=PrintJobStatus.PRINTED,
        content=content,
        printed_at=printed_at,
    )

    return job
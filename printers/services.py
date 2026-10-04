from collections import defaultdict
import socket
from django.conf import settings

from django.db import transaction
from django.utils import timezone

from orders.models import Order, OrderItem
from printers.models import (
    MessageToPrinter,
    PrintJob,
    PrintJobStatus,
    Printer,
)


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

        # Center
        data += b"\x1b\x61\x01"

        # Bold ON
        data += b"\x1b\x45\x01"

        data += b"RESTAURANT TEST\n"

        # Bold OFF
        data += b"\x1b\x45\x00"

        data += b"\n"
        data += b"Printer connection OK\n"
        data += b"\n\n\n"

        # Cut paper
        data += b"\x1d\x56\x01"

        self.send(data)


# ============================================================
# TEXT -> ESC/POS
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

    # Encode text
    data += content.encode(
        "utf-8",
        errors="replace",
    )

    # Feed paper
    data += b"\n\n\n"

    # Cut
    data += b"\x1d\x56\x01"

    return data


# ============================================================
# BUILD ORDER TICKET
# ============================================================

def build_order_item_ticket(
    order,
    section,
    items,
    width: int = 42,
) -> str:
    """
    Build a kitchen/bar/etc. ticket for the selected section.
    """

    now = timezone.localtime()

    lines = []

    def separator(char="-"):
        return char * width

    def centered(text):
        return str(text).center(width)

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    lines.append(
        centered("RESTAURANT")
    )

    lines.append(
        centered(str(section.name))
    )

    lines.append(
        separator("=")
    )

    # --------------------------------------------------------
    # TABLE
    # --------------------------------------------------------

    table = getattr(order, "table", None)

    if table:
        table_number = getattr(
            table,
            "table_number",
            "-"
        )

        table_name = getattr(
            table,
            "name",
            ""
        )

        if table_name:
            lines.append(
                f"TABLE   : {table_name}"
            )

        lines.append(
            f"TABLE # : {table_number}"
        )

    # --------------------------------------------------------
    # WAITER
    # --------------------------------------------------------

    waiter = getattr(order, "waiter", None)

    if waiter:

        waiter_name = (
            getattr(
                waiter,
                "full_name",
                None,
            )
            or getattr(
                waiter,
                "username",
                None,
            )
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
    # ORDER
    # --------------------------------------------------------

    lines.append(
        f"ORDER # : {order.id}"
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

    lines.append(
        separator("=")
    )

    # --------------------------------------------------------
    # ITEMS
    # --------------------------------------------------------

    for item in items:

        product_name = str(item.product.name)

        quantity = item.quantity

        lines.append(
            f"{quantity:g} x {product_name}"
        )

        if item.notes:

            for note_line in str(
                item.notes
            ).splitlines():

                lines.append(
                    f"  NOTE: {note_line}"
                )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    lines.append(
        separator("=")
    )

    lines.append(
        centered("KITCHEN ORDER")
    )

    lines.append("")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# CREATE PRINT JOBS
# ============================================================

def enqueue_print_jobs_for_order(
    order: Order,
) -> list[PrintJob]:
    """
    Create PrintJob records for all OrderItems that
    have not successfully printed yet.

    IMPORTANT:

    This function ONLY creates PrintJob records.

    It does NOT mark OrderItems as printed.

    OrderItem.has_print_job becomes True ONLY after
    process_print_job() successfully sends the ticket.
    """

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

    # --------------------------------------------------------
    # Group items by section
    # --------------------------------------------------------

    for item in pending_items:

        section_id = item.product.section_id

        if not section_id:
            continue

        grouped[section_id].append(item)

    jobs = []

    with transaction.atomic():

        for section_id, items in grouped.items():

            # ------------------------------------------------
            # Find active printer for section
            # ------------------------------------------------

            printer = (
                Printer.objects
                .filter(
                    section_id=section_id,
                    is_active=True,
                )
                .select_related("section")
                .first()
            )

            if printer is None:
                continue

            # ------------------------------------------------
            # Build ticket
            # ------------------------------------------------

            content = build_order_item_ticket(
                order=order,
                section=printer.section,
                items=items,
            )

            # ------------------------------------------------
            # Create PrintJob
            # ------------------------------------------------

            job = PrintJob.objects.create(
                order=order,
                section=printer.section,
                printer=printer,
                status=PrintJobStatus.PENDING,
                content=content,
            )

            # ------------------------------------------------
            # IMPORTANT
            #
            # PrintJob.order_items is ManyToMany.
            #
            # Therefore we MUST use .set()
            # AFTER creating the PrintJob.
            # ------------------------------------------------

            job.order_items.set(items)

            jobs.append(job)

    return jobs


# ============================================================
# PROCESS ONE PRINT JOB
# ============================================================
from django.utils import timezone
from printers.models import PrintJob, PrintJobStatus


def process_print_job(job: PrintJob) -> PrintJob:
    # Refresh to inspect current DB state
    job.refresh_from_db()

    # Prevent processing if already printed or currently being processed
    if job.status in [PrintJobStatus.PRINTED, PrintJobStatus.PRINTING]:
        print(f"[PRINT] PrintJob #{job.id} is already in status '{job.status}'. Skipping.")
        return job

    # Mark status as PRINTING immediately to avoid race conditions
    job.status = PrintJobStatus.PRINTING
    job.error_message = ""
    job.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
    )

    try:
        printer = job.printer

        if not printer:
            raise ValueError("No printer assigned to this PrintJob.")

        if not printer.is_active:
            raise ValueError(f"Printer '{printer.name}' is inactive.")

        if printer.connection_type != "NETWORK":
            raise ValueError(f"Printer '{printer.name}' is not a network printer.")

        if not printer.ip_address:
            raise ValueError(f"Printer '{printer.name}' does not have an IP address.")

        if not job.content or not job.content.strip():
            raise ValueError(f"PrintJob #{job.id} has empty content.")

        # Initialize network ESC/POS connection
        device = ESCPosPrinter(
            host=str(printer.ip_address),
            port=printer.port or 9100,
            timeout=5,
        )

        receipt_data = text_to_escpos(job.content)

        # ========================================================
        # SEND TO PHYSICAL PRINTER
        # ========================================================

        print(
            f"[PRINT] Sending PrintJob #{job.id} "
            f"to {printer.name} ({printer.ip_address}:{printer.port})"
        )

        device.send(receipt_data)

        print(f"[PRINT] PrintJob #{job.id} sent successfully.")

        # ========================================================
        # MARK JOB AS PRINTED
        # ========================================================

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

        # ========================================================
        # MARK ATTACHED ORDER ITEMS (IF ANY EXIST)
        # ========================================================

        order_items = list(job.order_items.all())

        if order_items:
            print(
                f"[PRINT] PrintJob #{job.id} has "
                f"{len(order_items)} attached OrderItem(s): {[item.id for item in order_items]}"
            )

            for item in order_items:
                item.set_as_printed()
                print(f"[PRINT] OrderItem #{item.id} has_print_job=True")
        else:
            # Cancellation tickets or direct message jobs won't have attached OrderItems
            print(f"[PRINT] PrintJob #{job.id} completed with 0 attached OrderItems (e.g. cancellation/message ticket).")

    except Exception as exc:
        job.status = PrintJobStatus.FAILED
        job.retry_count += 1
        job.error_message = str(exc)[:1000]

        job.save(
            update_fields=[
                "status",
                "retry_count",
                "error_message",
                "updated_at",
            ]
        )

        print(f"[PRINT ERROR] PrintJob #{job.id} failed: {job.error_message}")

    return job

def process_print_job1(job):

    print("=" * 60)
    print(
        f"[PRINT] Processing PrintJob #{job.id}"
    )

    try:

        # -----------------------------------------------------
        # Mark as printing
        # -----------------------------------------------------

        job.status = PrintJobStatus.PRINTING
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

        # -----------------------------------------------------
        # THE ONLY PRINTABLE DATA WE NEED
        # -----------------------------------------------------

        content = job.content

        if not content:
            raise ValueError(
                "PrintJob has empty content."
            )

        print(
            f"[PRINT] Content length: "
            f"{len(content)}"
        )

        print(
            "[PRINT] Content:"
        )

        print(content)

        # -----------------------------------------------------
        # SEND CONTENT TO YOUR EXISTING PRINTER FUNCTION
        # -----------------------------------------------------

        send_to_printer(
            printer=job.printer,
            content=content,
        )

        # -----------------------------------------------------
        # SUCCESS
        # -----------------------------------------------------

        job.status = PrintJobStatus.PRINTED
        job.printed_at = timezone.now()

        job.save(
            update_fields=[
                "status",
                "printed_at",
                "updated_at",
            ]
        )

        print(
            f"[PRINT] PrintJob #{job.id} "
            f"printed successfully."
        )

        return True

    except Exception as exc:

        job.status = PrintJobStatus.FAILED
        job.error_message = str(exc)
        job.retry_count += 1

        job.save(
            update_fields=[
                "status",
                "error_message",
                "retry_count",
                "updated_at",
            ]
        )

        print(
            f"[PRINT] PrintJob #{job.id} FAILED: "
            f"{exc}"
        )

        return False
# ============================================================
# PRINT ALL PENDING ITEMS FOR ORDER
# ============================================================

def print_pending_items_for_order(
    order: Order,
) -> list[PrintJob]:
    """
    Create and immediately process all pending
    OrderItem print jobs.
    """

    # --------------------------------------------------------
    # Create jobs
    # --------------------------------------------------------

    jobs = enqueue_print_jobs_for_order(
        order
    )

    if not jobs:
        return []

    processed_jobs = []

    # --------------------------------------------------------
    # Process each job
    # --------------------------------------------------------

    for job in jobs:

        processed_job = process_print_job(
            job
        )

        processed_jobs.append(
            processed_job
        )

    return processed_jobs


# ============================================================
# TEST PRINTER
# ============================================================

def test_printer(
    printer: Printer,
):

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
        host=str(printer.ip_address),
        port=printer.port or 9100,
        timeout=5,
    )

    device.test()


# ============================================================
# MESSAGE TO PRINTER
# ============================================================

def build_message_ticket(
    message: MessageToPrinter,
    width: int = 42,
) -> str:

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

    lines.append(
        centered("RESTAURANT")
    )

    lines.append(
        separator("=")
    )

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
            getattr(
                waiter,
                "full_name",
                None,
            )
            or getattr(
                waiter,
                "username",
                None,
            )
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

    lines.append(
        separator("=")
    )

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    lines.append(
        centered("MESSAGE")
    )

    lines.append(
        separator("-")
    )

    for line in str(
        message.message
    ).splitlines():

        lines.append(line)

    lines.append(
        separator("-")
    )

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
            f"has no IP address."
        )

    # --------------------------------------------------------
    # Build ticket
    # --------------------------------------------------------

    content = build_message_ticket(
        message
    )

    try:

        device = ESCPosPrinter(
            host=str(printer.ip_address),
            port=printer.port or 9100,
            timeout=5,
        )

        receipt_data = text_to_escpos(
            content
        )

        device.send(
            receipt_data
        )

    except Exception as exc:

        # NOTE:
        # Your MessageToPrinter model as posted does NOT
        # contain is_printed / printed_at / error_message.
        #
        # Therefore we don't update those fields here.
        #
        # We create a FAILED PrintJob instead.

        job = PrintJob.objects.create(
            order=None,
            section=printer.section,
            printer=printer,
            status=PrintJobStatus.FAILED,
            content=content,
            error_message=str(exc)[:1000],
        )

        return job

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    printed_at = timezone.now()

    job = PrintJob.objects.create(
        order=None,
        section=printer.section,
        printer=printer,
        status=PrintJobStatus.PRINTED,
        content=content,
        printed_at=printed_at,
    )

    return job
from collections import OrderedDict
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from printers.models import (
    ConnectionType,
    PrintJob,
    PrintJobStatus,
    Printer,
)


# ============================================================
# CUSTOMER INVOICE
# ============================================================

def build_customer_invoice(
    order,
    width: int = 42,
) -> str:
    """
    Build customer invoice / receipt.

    Repeated products are merged into one line.

    Example:

        Chicken       2   250.00     500.00

    instead of:

        Chicken       1   250.00     250.00
        Chicken       1   250.00     250.00
    """

    now = timezone.localtime()

    lines = []

    # ========================================================
    # HELPERS
    # ========================================================

    def separator(char="-"):
        return char * width

    def centered(text):
        return str(text).center(width)

    def money(value):
        """
        Format a numeric value without currency.
        Used for product rows.
        """
        return f"{Decimal(value):.2f}"

    def currency(value):
        """
        Format a numeric value with the configured currency.

        Example:
            1050.00 ₺
        """
        return (
            f"{Decimal(value):.2f} "
            f"{settings.TRY}"
        )

    def total_line(label, value):
        """
        Build a right-aligned total line.

        Example:
            SUBTOTAL                    1050.00 ₺
        """
        amount = currency(value)

        label_width = width - len(amount)

        return (
            f"{label:<{label_width}}"
            f"{amount:>{len(amount)}}"
        )

    def negative_total_line(label, value):
        """
        Build a right-aligned negative amount.

        Example:
            DISCOUNT                   -100.00 ₺
        """
        amount = f"-{currency(value)}"

        label_width = width - len(amount)

        return (
            f"{label:<{label_width}}"
            f"{amount:>{len(amount)}}"
        )

    # ========================================================
    # HEADER
    # ========================================================

    lines.append(
        centered("RESTAURANT")
    )

    lines.append(
        separator("=")
    )

    # ========================================================
    # TABLE
    # ========================================================

    table = getattr(
        order,
        "table",
        None,
    )

    if table:

        table_name = getattr(
            table,
            "name",
            "",
        )

        table_number = getattr(
            table,
            "table_number",
            "-",
        )

        if table_name:
            lines.append(
                f"TABLE   : {table_name}"
            )

        lines.append(
            f"TABLE # : {table_number}"
        )

    # ========================================================
    # ORDER
    # ========================================================

    lines.append(
        f"ORDER # : {order.id}"
    )

    # ========================================================
    # WAITER
    # ========================================================

    waiter = getattr(
        order,
        "waiter",
        None,
    )

    if waiter:

        waiter_name = (
            getattr(
                waiter,
                "full_name",
                None,
            )
            or getattr(
                waiter,
                "username",
                None,
            )
            or str(waiter)
        )

    else:

        waiter_name = "-"

    lines.append(
        f"WAITER  : {waiter_name}"
    )

    # ========================================================
    # DATE / TIME
    # ========================================================

    lines.append(
        f"DATE    : {now.strftime('%Y-%m-%d')}"
    )

    lines.append(
        f"TIME    : {now.strftime('%H:%M:%S')}"
    )

    lines.append(
        separator("=")
    )

    # ========================================================
    # MERGE PRODUCTS
    # ========================================================

    merged_items = OrderedDict()

    order_items = (
        order.items
        .select_related("product")
        .all()
    )

    for item in order_items:

        product_id = item.product_id

        if product_id not in merged_items:

            merged_items[product_id] = {
                "name": str(
                    item.product.name
                ),
                "quantity": Decimal("0"),
                "unit_price": Decimal(
                    item.unit_price
                ),
                "total": Decimal("0"),
            }

        merged_items[product_id]["quantity"] += (
            Decimal(item.quantity)
        )

        merged_items[product_id]["total"] += (
            Decimal(item.quantity)
            * Decimal(item.unit_price)
        )

    # ========================================================
    # ITEMS HEADER
    # ========================================================

    lines.append(
        f"{'ITEM':<18}"
        f"{'QTY':>5}"
        f"{'PRICE':>9}"
        f"{'TOTAL':>10}"
    )

    lines.append(
        separator("-")
    )

    # ========================================================
    # ITEMS
    # ========================================================

    calculated_subtotal = Decimal("0")

    for item in merged_items.values():

        name = item["name"]

        quantity = item["quantity"]

        unit_price = item["unit_price"]

        item_total = item["total"]

        calculated_subtotal += item_total

        # ----------------------------------------------------
        # Keep product name within receipt width.
        # ----------------------------------------------------

        name = name[:18]

        lines.append(
            f"{name:<18}"
            f"{quantity:>5g}"
            f"{money(unit_price):>9}"
            f"{money(item_total):>10}"
        )

    lines.append(
        separator("-")
    )

    # ========================================================
    # ORDER TOTALS
    # ========================================================

    order_subtotal = Decimal(
        getattr(
            order,
            "subtotal",
            calculated_subtotal,
        )
        or calculated_subtotal
    )

    discount = Decimal(
        getattr(
            order,
            "discount",
            0,
        )
        or 0
    )

    tax = Decimal(
        getattr(
            order,
            "tax",
            0,
        )
        or 0
    )

    total_value = getattr(
        order,
        "total",
        None,
    )

    if total_value is not None:

        total = Decimal(
            total_value
        )

    else:

        total = (
            order_subtotal
            - discount
            + tax
        )

    # ========================================================
    # SUBTOTAL
    # ========================================================

    lines.append(
        total_line(
            "SUBTOTAL",
            order_subtotal,
        )
    )

    # ========================================================
    # DISCOUNT
    # ========================================================

    if discount > 0:

        lines.append(
            negative_total_line(
                "DISCOUNT",
                discount,
            )
        )

    # ========================================================
    # TAX
    # ========================================================

    if tax > 0:

        lines.append(
            total_line(
                "TAX",
                tax,
            )
        )

    # ========================================================
    # TOTAL
    # ========================================================

    lines.append(
        separator("=")
    )

    lines.append(
        total_line(
            "TOTAL",
            total,
        )
    )

    lines.append(
        separator("=")
    )

    # ========================================================
    # FOOTER
    # ========================================================

    lines.append(
        centered("THANK YOU!")
    )

    lines.append("")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# PRINT CUSTOMER INVOICE
# ============================================================

def print_customer_invoice(
    order,
) -> PrintJob:
    """
    Create and print a customer invoice.

    The printer is selected using:

        is_cashier=True
        is_active=True

    The invoice is created as a normal PrintJob and then
    processed through process_print_job().
    """

    # ========================================================
    # FIND CASHIER / CUSTOMER INVOICE PRINTER
    # ========================================================

    printer = (
        Printer.objects
        .filter(
            is_cashier=True,
            is_active=True,
        )
        .order_by("id")
        .first()
    )

    if printer is None:

        raise ValueError(
            "No active cashier printer configured."
        )

    # ========================================================
    # VALIDATE CONNECTION TYPE
    # ========================================================

    if printer.connection_type != ConnectionType.NETWORK:

        raise ValueError(
            f"Printer '{printer.name}' "
            f"is not a network printer."
        )

    # ========================================================
    # VALIDATE IP ADDRESS
    # ========================================================

    if not printer.ip_address:

        raise ValueError(
            f"Printer '{printer.name}' "
            f"has no IP address."
        )

    # ========================================================
    # BUILD INVOICE
    # ========================================================

    content = build_customer_invoice(
        order=order,
        width=42,
    )

    # ========================================================
    # CREATE PRINT JOB
    # ========================================================

    job = PrintJob.objects.create(
        order=order,
        section=printer.section,
        printer=printer,
        status=PrintJobStatus.PENDING,
        content=content,
    )

    # ========================================================
    # PROCESS PRINT JOB
    # ========================================================

    return process_print_job(job)




def create_cancelled_item_print_job(order_item):
    """
    Create a print job for an already-printed order item
    that is being cancelled/deleted.

    If the item was never printed, no cancellation ticket
    is created.
    """

    if not order_item.has_print_job:
        return None

    product = order_item.product
    section = product.section

    if section is None:
        return None

    printer = (
        Printer.objects
        .filter(
            section=section,
            is_active=True,
        )
        .first()
    )

    if printer is None:
        return None

    order = order_item.order

    # ---------------------------------------------------------
    # Build cancellation ticket
    # ---------------------------------------------------------

    content_lines = [
        "========== CANCELLATION ==========",
        f"TABLE: {order.table.number}",
        f"WAITER: {order.waiter.full_name}",
        "",
        f"X {order_item.quantity}  {product.name}",
    ]

    if order_item.notes:
        content_lines.append(
            f"NOTE: {order_item.notes}"
        )

    content_lines.extend(
        [
            "",
            "!!! CANCELLED ITEM !!!",
            "==================================",
        ]
    )

    content = "\n".join(content_lines)

    # ---------------------------------------------------------
    # Create a NEW print job
    # ---------------------------------------------------------

    job = PrintJob.objects.create(
        order_id=order.id,
        section=section,
        printer=printer,
        status=PrintJobStatus.PENDING,
        content=content,
    )

    return job


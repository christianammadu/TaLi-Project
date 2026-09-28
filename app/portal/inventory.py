"""Inventory and product catalog management for the Merchant Web Portal (WP-09).

Supports listing, adding products, restocking, stock adjustments, and low-stock warnings.
All operations are strictly multi-tenant isolated by merchant user_id.
"""

from decimal import Decimal
from sqlalchemy import func, or_, select, update

from app.data.db import session_scope
from app.data.models import InventoryItem, InventoryMovement, Product, StockMovement
from app.services.uuid_utils import uuid7


def get_merchant_inventory_items(
    user_id: str,
    search: str = None,
    low_stock_only: bool = False,
) -> list[dict]:
    """Retrieve all catalog items owned by the merchant.

    Returns:
        List of item dictionaries with stock levels, units, and status badges.
    """
    items = []
    seen_names = set()

    try:
        with session_scope() as s:
            # 1. Query products table
            stmt_p = select(Product).where(Product.user_id == user_id)
            if search:
                term = f"%{search.strip()}%"
                stmt_p = stmt_p.where(Product.name.ilike(term))

            prods = s.execute(stmt_p.order_by(Product.name.asc())).scalars().all()
            for p in prods:
                qty = float(p.quantity or 0)
                min_stock = 5.0  # default threshold
                is_low = qty <= min_stock
                status = "OUT_OF_STOCK" if qty <= 0 else ("LOW_STOCK" if is_low else "IN_STOCK")

                items.append({
                    "id": str(p.id),
                    "name": p.name,
                    "unit": p.unit or "pcs",
                    "quantity": qty,
                    "min_stock": min_stock,
                    "is_low_stock": is_low,
                    "status": status,
                    "source": "products",
                    "created_at": p.created_at.strftime("%Y-%m-%d") if p.created_at else "",
                })
                seen_names.add(p.name.strip().lower())

            # 2. Query inventory_items table for items not yet covered in products
            stmt_i = select(InventoryItem).where(InventoryItem.user_id == user_id)
            if search:
                term = f"%{search.strip()}%"
                stmt_i = stmt_i.where(InventoryItem.item_name.ilike(term))

            inv_items = s.execute(stmt_i.order_by(InventoryItem.item_name.asc())).scalars().all()
            for item in inv_items:
                clean_name = item.item_name.strip().lower()
                if clean_name in seen_names:
                    continue

                min_stock = float(item.minimum_stock_level or 5)
                # Compute balance from movements
                qty_in = s.execute(
                    select(func.coalesce(func.sum(InventoryMovement.quantity), 0))
                    .where(
                        InventoryMovement.inventory_item_id == item.id,
                        InventoryMovement.movement_type == "stock_in",
                    )
                ).scalar() or 0
                qty_out = s.execute(
                    select(func.coalesce(func.sum(InventoryMovement.quantity), 0))
                    .where(
                        InventoryMovement.inventory_item_id == item.id,
                        InventoryMovement.movement_type == "stock_out",
                    )
                ).scalar() or 0

                net_qty = float(qty_in) - float(qty_out)
                is_low = net_qty <= min_stock
                status = "OUT_OF_STOCK" if net_qty <= 0 else ("LOW_STOCK" if is_low else "IN_STOCK")

                items.append({
                    "id": str(item.id),
                    "name": item.item_name,
                    "unit": item.unit or "pcs",
                    "quantity": net_qty,
                    "min_stock": min_stock,
                    "is_low_stock": is_low,
                    "status": status,
                    "source": "inventory_items",
                    "created_at": item.created_at.strftime("%Y-%m-%d") if item.created_at else "",
                })
                seen_names.add(clean_name)

    except Exception as e:
        print(f"Error querying merchant inventory: {e}")

    if low_stock_only:
        items = [i for i in items if i["is_low_stock"]]

    return sorted(items, key=lambda x: (not x["is_low_stock"], x["name"].lower()))


def add_merchant_inventory_item(
    user_id: str,
    name: str,
    unit: str = "pcs",
    initial_quantity: float = 0.0,
    min_stock: float = 5.0,
) -> tuple[bool, str, dict | None]:
    """Add a new product or inventory item for the merchant."""
    clean_name = name.strip() if name else ""
    if not clean_name:
        return False, "Product name is required.", None

    if len(clean_name) > 100:
        return False, "Product name must be 100 characters or fewer.", None

    try:
        qty_dec = Decimal(str(initial_quantity or 0))
    except (ValueError, TypeError):
        qty_dec = Decimal("0.00")

    try:
        min_dec = Decimal(str(min_stock or 5))
    except (ValueError, TypeError):
        min_dec = Decimal("5.00")

    clean_unit = (unit.strip() if unit else "pcs")[:50]

    try:
        with session_scope() as s:
            # Check if item with exact name already exists for this user
            existing = s.execute(
                select(Product).where(
                    Product.user_id == user_id,
                    func.lower(Product.name) == clean_name.lower(),
                )
            ).scalars().first()

            if existing:
                return False, f"Product '{clean_name}' already exists in your catalog.", None

            item_id = uuid7()
            prod = Product(
                id=item_id,
                user_id=user_id,
                name=clean_name,
                quantity=qty_dec,
                unit=clean_unit,
            )
            s.add(prod)

            # Also mirror to inventory_items
            inv_item = InventoryItem(
                id=item_id,
                user_id=user_id,
                item_name=clean_name,
                unit=clean_unit,
                minimum_stock_level=min_dec,
            )
            s.add(inv_item)

            if qty_dec > 0:
                s.add(
                    StockMovement(
                        id=uuid7(),
                        product_id=item_id,
                        user_id=user_id,
                        movement_type="set",
                        quantity=qty_dec,
                        description="Initial stock record from web portal",
                    )
                )

            s.commit()
            return True, f"Product '{clean_name}' added successfully.", {
                "id": str(item_id),
                "name": clean_name,
                "unit": clean_unit,
                "quantity": float(qty_dec),
            }

    except Exception as e:
        print(f"Error adding inventory item: {e}")
        return False, "Failed to create product due to a server error.", None


def adjust_merchant_stock(
    user_id: str,
    item_id: str,
    adjustment_type: str,
    quantity: float,
    notes: str = None,
) -> tuple[bool, str, float]:
    """Adjust current inventory stock level (restock, loss/damage, count correction).

    Returns:
        (success: bool, message: str, new_quantity: float)
    """
    try:
        delta = Decimal(str(quantity or 0))
    except (ValueError, TypeError):
        return False, "Invalid adjustment quantity.", 0.0

    if delta <= 0 and adjustment_type != "set":
        return False, "Adjustment quantity must be greater than zero.", 0.0

    adj = adjustment_type.strip().lower()

    try:
        with session_scope() as s:
            # Look up product
            prod = s.execute(
                select(Product).where(Product.user_id == user_id, Product.id == item_id)
            ).scalars().first()

            if not prod:
                # Try finding in inventory_items
                inv = s.execute(
                    select(InventoryItem).where(InventoryItem.user_id == user_id, InventoryItem.id == item_id)
                ).scalars().first()
                if not inv:
                    return False, "Item not found in your catalog.", 0.0

                # Create matching product entry if missing
                prod = Product(
                    id=inv.id,
                    user_id=user_id,
                    name=inv.item_name,
                    quantity=Decimal("0.00"),
                    unit=inv.unit or "pcs",
                )
                s.add(prod)

            old_qty = Decimal(str(prod.quantity or 0))
            if adj in ("restock", "add", "stock_in"):
                new_qty = old_qty + delta
                mov_type = "in"
                desc = notes or f"Restocked +{delta} {prod.unit or 'pcs'}"
            elif adj in ("remove", "damage", "loss", "stock_out"):
                new_qty = max(Decimal("0.00"), old_qty - delta)
                mov_type = "out"
                desc = notes or f"Stock reduced -{delta} {prod.unit or 'pcs'}"
            elif adj in ("set", "correction"):
                new_qty = max(Decimal("0.00"), delta)
                mov_type = "set"
                desc = notes or f"Stock count updated to {new_qty} {prod.unit or 'pcs'}"
            else:
                return False, f"Unknown adjustment type '{adjustment_type}'.", float(old_qty)

            prod.quantity = new_qty
            s.add(
                StockMovement(
                    id=uuid7(),
                    product_id=prod.id,
                    user_id=user_id,
                    movement_type=mov_type,
                    quantity=delta,
                    description=desc,
                )
            )

            s.commit()
            return True, f"Stock updated to {float(new_qty)} {prod.unit or 'pcs'}.", float(new_qty)

    except Exception as e:
        print(f"Error adjusting stock: {e}")
        return False, "Failed to update stock due to an internal error.", 0.0


def get_inventory_summary_stats(user_id: str) -> dict:
    """Compute catalog health statistics."""
    items = get_merchant_inventory_items(user_id)
    total = len(items)
    low = sum(1 for i in items if i["status"] == "LOW_STOCK")
    out = sum(1 for i in items if i["status"] == "OUT_OF_STOCK")
    in_stock = total - low - out

    return {
        "total_skus": total,
        "in_stock": in_stock,
        "low_stock": low,
        "out_of_stock": out,
    }

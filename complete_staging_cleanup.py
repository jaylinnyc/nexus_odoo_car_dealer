# Complete Staging Data Cleanup - Copy-paste into Odoo.sh shell
# This script deletes all transactional data from staging database
# Created: December 30, 2025
# Updated: December 31, 2025
# Usage: Copy entire script and paste into Odoo.sh shell

print("\n" + "="*80)
print("COMPLETE STAGING DATA CLEANUP")
print("="*80 + "\n")

try:
    # STEP 1: Delete Payments
    print("[1/13] Deleting payments...")
    env.cr.execute("SELECT COUNT(*) FROM account_payment")
    payment_count = env.cr.fetchone()[0]
    if payment_count > 0:
        env.cr.execute("DELETE FROM account_payment")
        print(f"  ✓ Deleted {env.cr.rowcount} payment(s)")
    else:
        print("  ✓ No payments to delete")
    
    # STEP 2: Delete Sale Orders
    print("[2/13] Deleting sale orders...")
    env.cr.execute("SELECT COUNT(*) FROM sale_order")
    so_count = env.cr.fetchone()[0]
    if so_count > 0:
        env.cr.execute("DELETE FROM sale_order_line")
        print(f"  ✓ Deleted {env.cr.rowcount} sale order line(s)")
        env.cr.execute("DELETE FROM sale_order")
        print(f"  ✓ Deleted {env.cr.rowcount} sale order(s)")
    else:
        print("  ✓ No sale orders to delete")
    
    # STEP 3: Delete Purchase Orders
    print("[3/13] Deleting purchase orders...")
    env.cr.execute("SELECT COUNT(*) FROM purchase_order")
    po_count = env.cr.fetchone()[0]
    if po_count > 0:
        env.cr.execute("DELETE FROM purchase_order_line")
        print(f"  ✓ Deleted {env.cr.rowcount} purchase order line(s)")
        env.cr.execute("DELETE FROM purchase_order")
        print(f"  ✓ Deleted {env.cr.rowcount} purchase order(s)")
    else:
        print("  ✓ No purchase orders to delete")
    
    # STEP 4: Delete Stock Moves
    print("[4/13] Deleting stock moves...")
    env.cr.execute("SELECT COUNT(*) FROM stock_move")
    move_count = env.cr.fetchone()[0]
    if move_count > 0:
        env.cr.execute("DELETE FROM stock_move_line")
        print(f"  ✓ Deleted {env.cr.rowcount} stock move line(s)")
        env.cr.execute("DELETE FROM stock_move")
        print(f"  ✓ Deleted {env.cr.rowcount} stock move(s)")
    else:
        print("  ✓ No stock moves to delete")
    
    # STEP 5: Delete Stock Pickings
    print("[5/13] Deleting stock pickings...")
    env.cr.execute("SELECT COUNT(*) FROM stock_picking")
    picking_count = env.cr.fetchone()[0]
    if picking_count > 0:
        env.cr.execute("DELETE FROM stock_picking")
        print(f"  ✓ Deleted {env.cr.rowcount} stock picking(s)")
    else:
        print("  ✓ No stock pickings to delete")
    
    # STEP 6: Delete Stock Quants
    print("[6/13] Deleting stock quants...")
    env.cr.execute("SELECT COUNT(*) FROM stock_quant")
    quant_count = env.cr.fetchone()[0]
    if quant_count > 0:
        env.cr.execute("DELETE FROM stock_quant")
        print(f"  ✓ Deleted {env.cr.rowcount} stock quant(s)")
    else:
        print("  ✓ No stock quants to delete")
    
    # STEP 7: Delete Stock Lots
    print("[7/13] Deleting stock lots...")
    env.cr.execute("SELECT COUNT(*) FROM stock_lot")
    lot_count = env.cr.fetchone()[0]
    if lot_count > 0:
        env.cr.execute("DELETE FROM stock_lot")
        print(f"  ✓ Deleted {env.cr.rowcount} stock lot(s)")
    else:
        print("  ✓ No stock lots to delete")
    
    # STEP 8: Delete Account Partial Reconciliations (CRITICAL - must come before account moves)
    print("[8/13] Deleting account partial reconciliations...")
    env.cr.execute("SELECT COUNT(*) FROM account_partial_reconcile")
    reconcile_count = env.cr.fetchone()[0]
    if reconcile_count > 0:
        env.cr.execute("DELETE FROM account_partial_reconcile")
        print(f"  ✓ Deleted {env.cr.rowcount} partial reconciliation(s)")
    else:
        print("  ✓ No partial reconciliations to delete")
    
    # STEP 9: Delete Account Moves
    print("[9/13] Deleting account moves (bills, invoices, journal entries)...")
    env.cr.execute("SELECT COUNT(*) FROM account_move")
    move_count = env.cr.fetchone()[0]
    if move_count > 0:
        env.cr.execute("DELETE FROM account_move_line")
        print(f"  ✓ Deleted {env.cr.rowcount} account move line(s)")
        env.cr.execute("DELETE FROM account_move")
        print(f"  ✓ Deleted {env.cr.rowcount} account move(s)")
    else:
        print("  ✓ No account moves to delete")
    
    # STEP 10: Delete Financing Records
    print("[10/13] Deleting financing records...")
    env.cr.execute("SELECT COUNT(*) FROM vehicle_financing")
    financing_count = env.cr.fetchone()[0]
    if financing_count > 0:
        env.cr.execute("DELETE FROM vehicle_financing")
        print(f"  ✓ Deleted {env.cr.rowcount} financing record(s)")
    else:
        print("  ✓ No financing records to delete")
    
    # STEP 11: Delete Financing Transactions
    print("[11/13] Deleting financing transactions...")
    env.cr.execute("SELECT COUNT(*) FROM vehicle_financing_transaction")
    trans_count = env.cr.fetchone()[0]
    if trans_count > 0:
        env.cr.execute("DELETE FROM vehicle_financing_transaction")
        print(f"  ✓ Deleted {env.cr.rowcount} financing transaction(s)")
    else:
        print("  ✓ No financing transactions to delete")
    
    # STEP 12: Delete Stock Valuation Adjustment Lines
    print("[12/13] Deleting stock valuation adjustment lines...")
    env.cr.execute("SELECT COUNT(*) FROM stock_valuation_adjustment_lines")
    val_adj_count = env.cr.fetchone()[0]
    if val_adj_count > 0:
        env.cr.execute("DELETE FROM stock_valuation_adjustment_lines")
        print(f"  ✓ Deleted {env.cr.rowcount} valuation adjustment line(s)")
    else:
        print("  ✓ No valuation adjustment lines to delete")
    
    env.cr.execute("SELECT COUNT(*) FROM stock_landed_cost")
    lc_count = env.cr.fetchone()[0]
    if lc_count > 0:
        env.cr.execute("DELETE FROM stock_landed_cost_lines")
        print(f"  ✓ Deleted {env.cr.rowcount} landed cost line(s)")
        env.cr.execute("DELETE FROM stock_landed_cost")
        print(f"  ✓ Deleted {env.cr.rowcount} landed cost(s)")
    
    # STEP 13: Delete Vehicle Products
    print("[13/13] Deleting vehicle products...")
    vehicles = env['product.product'].search([('product_tmpl_id.categ_id.name', '=', 'Vehicles')])
    vehicle_count = len(vehicles)
    
    if vehicle_count > 0:
        vehicle_ids = tuple(vehicles.ids)
        env.cr.execute("SELECT DISTINCT product_tmpl_id FROM product_product WHERE id IN %s", (vehicle_ids,))
        template_ids = tuple([r[0] for r in env.cr.fetchall()])
        env.cr.execute("DELETE FROM product_product WHERE id IN %s", (vehicle_ids,))
        print(f"  ✓ Deleted {env.cr.rowcount} vehicle product variant(s)")
        if template_ids:
            env.cr.execute("DELETE FROM product_template WHERE id IN %s", (template_ids,))
            print(f"  ✓ Deleted {env.cr.rowcount} vehicle product template(s)")
    else:
        print("  ✓ No vehicle products to delete")
    
    # COMMIT
    env.cr.commit()
    
    print("\n" + "="*80)
    print("✅ SUCCESS: All staging data deleted!")
    print("="*80 + "\n")
    
    # VERIFICATION
    print("📊 VERIFICATION:")
    env.cr.execute("SELECT COUNT(*) FROM account_payment")
    print(f"  • Payments: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM account_move")
    print(f"  • Account moves: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM sale_order")
    print(f"  • Sale orders: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM purchase_order")
    print(f"  • Purchase orders: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM stock_move")
    print(f"  • Stock moves: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM stock_quant")
    print(f"  • Stock quants: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM vehicle_financing")
    print(f"  • Financing records: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM account_partial_reconcile")
    print(f"  • Partial reconciliations: {env.cr.fetchone()[0]}")
    env.cr.execute("SELECT COUNT(*) FROM product_product pp JOIN product_template pt ON pp.product_tmpl_id = pt.id WHERE pt.categ_id IN (SELECT id FROM product_category WHERE name = 'Vehicles')")
    print(f"  • Vehicle products: {env.cr.fetchone()[0]}")
    print("\n✅ Cleanup complete!\n")

except Exception as e:
    env.cr.rollback()
    print(f"\n❌ ERROR: {str(e)}")
    print("💡 Transaction rolled back. Database unchanged.\n")
    raise

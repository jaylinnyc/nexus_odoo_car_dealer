/** @odoo-module **/

import { whenReady } from "@odoo/owl";
import { mountComponent } from "@web/env";
import { ProductInventory } from "./components/inventory";

function start() {
    const target = document.getElementById("root");
    whenReady(() => mountComponent(ProductInventory, target));
}

start();
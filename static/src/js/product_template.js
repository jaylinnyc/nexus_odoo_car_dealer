/** @odoo-module **/

import { whenReady } from "@odoo/owl";
import { mountComponent } from "@web/env";
import { Product } from "./components/product";

function start() {
    const target = document.getElementById("product_root");
    console.log(target)
    if (target) {
        whenReady(() => {
            // 🌟 FIX: Pass the target element inside the options object 🌟
            mountComponent(Product, {
                target: target
            });
            console.log("Product Detail Component Mounted successfully.");
        });
    } else {
        console.error("Mounting target #product_root not found. Check XML/Assets.");
    }
}

start();
/** @odoo-module **/

import {Component, xml, useState, onWillStart} from "@odoo/owl";
import {rpc} from "@web/core/network/rpc";

export class Product extends Component {

    static template = xml/*xml*/`
    <div class="o_product_detail_page mt-5">
            
            <t t-if="state.isLoading">
                <div class="alert alert-info text-center">Loading product details...</div>
            </t>
            <t t-elif="state.error">
                <div class="alert alert-danger">Error: <t t-esc="state.error"/></div>
            </t>
            
            <t t-else="">
                <t t-set="product" t-value="state.product"/>
                
                <div class="row">
                    <div class="col-lg-6 mb-4">
                        <div class="product-image-container p-3" style="background-color: var(--card-bg-dark); border-radius: 8px;">
                            <img 
                                t-attf-src="/web/image?model=product.template&amp;id={{product.id}}&amp;field=image_1024"
                                class="img-fluid rounded" 
                                t-att-alt="product.name"
                            />
                        </div>
                    </div>

                    <div class="col-lg-6 mb-4">
                        <div class="product-details-container p-4" style="background-color: var(--card-bg-dark); border-radius: 8px; color: var(--text-light);">
                            
                            <h1 class="display-4 text-light" t-esc="product.name"/>
                            <hr class="mb-4" style="border-color: var(--button-dark-bg);"/>
                            
                            <h2 class="text-success mb-4" style="color: var(--primary-yellow) !important;">
                                <span t-esc="this.formatPrice(product.list_price, product.currency_id and product.currency_id[1] or '$')"/>
                            </h2>

                            <div class="mb-4">
                                <t t-if="product.qty_available > 0">
                                    <span class="badge bg-success py-2 px-3">In Stock: <t t-esc="product.qty_available"/></span>
                                </t>
                                <t t-else="">
                                    <span class="badge bg-danger py-2 px-3">Sold Out</span>
                                </t>
                            </div>
                            
                            <div class="d-grid gap-2 d-md-block mb-5">
                                <button class="btn btn-warning btn-lg me-2" t-on-click="() => this.addToCart(product.id)" 
                                    t-att-disabled="product.qty_available &lt;= 0 ? 'disabled' : undefined">
                                    <i class="fa fa-shopping-cart me-2"/> Add to Cart
                                </button>
                                <a href="/shop" class="btn btn-outline-secondary btn-lg" style="color: var(--text-light); border-color: var(--button-dark-bg);">
                                    <i class="fa fa-undo me-2"/> Back to Store
                                </a>
                            </div>

                            <h3 class="h5 mt-4" style="color: var(--text-muted-dark);">Description</h3>
                            <div class="text-muted" style="color: var(--text-muted-dark) !important;">
                                <t t-raw="product.description or 'No detailed description available.'"/>
                            </div>
                        </div>
                    </div>
                </div>
            </t>
        </div>
        `;

    setup() {
        this.productId = this._getProductIdFromUrl();

        this.state = useState({
            product: null,
            isLoading: true,
            error: null,
        });
        onWillStart(this.fetchProductDetail);
    }

    async fetchProductDetail() {
        try {
            this.state.isLoading = true;
            this.state.product = await rpc("/api/product/" + this.productId);
        } catch (e) {
            this.state.error = "Could not load product details.";
        } finally {
            this.state.isLoading = false;
        }
    }

    _getProductIdFromUrl() {
        const path = window.location.pathname;
        const parts = path.split('/').filter(p => p);
        const idSegment = parts[parts.length - 1];
        const productId = parseInt(idSegment);
        return isNaN(productId) ? null : productId;
    }
}
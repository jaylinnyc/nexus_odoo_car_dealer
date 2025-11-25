/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

// 1. Get the original WebsiteSale widget class from the registry
const WebsiteSale = publicWidget.registry.WebsiteSale;

// 2. Define a NEW class that extends the original WebsiteSale widget
const CarReservationWidget = WebsiteSale.extend({

    // We explicitly define the events object here, merging with the parent's events
    events: Object.assign({}, WebsiteSale.prototype.events, {
        'click #reserve_now_btn': '_onReserveNowClick',
    }),

    /**
     * Handles the click event on the "Reserve Now" button.
     * Initiates the draft reservation via JSON-RPC call.
     * @param {Event} ev
     */
    _onReserveNowClick: async function (ev) {
        ev.preventDefault();
        const $form = this.$el.closest('form');
        const $button = $(ev.currentTarget);

        const productID = $form.find('input[name="product_id"]').val();

        if (!productID) {
            alert(_t("Error: Cannot find the specific car model (product ID) to reserve."));
            return;
        }

        $button.prop('disabled', true).addClass('disabled');
        $button.html('<span class="fa fa-spin fa-spinner me-2"></span> ' + _t("Reserving..."));

        let result;
        try {
            result = await jsonrpc('/car/reserve/init', {
                'product_id': productID,
            });

            if (result.error) {
                alert(result.error);
            } else if (result.reservation_id) {
                alert(_t(`Reservation initiated for a deposit of ${result.deposit_amount}. Proceeding to payment.`));
                window.location.href = result.redirect_url + '?reservation_id=' + result.reservation_id;
            }
        } catch (error) {
            console.error("Reservation RPC Error:", error);
            alert(_t("An unexpected error occurred. Please check network connection or server logs."));
        } finally {
            if (!result || result.error) {
                $button.prop('disabled', false).removeClass('disabled');
                $button.text(_t("Reserve Now"));
            }
        }
    },
});

// 3. Register the new widget class, replacing the old one
// This is the correct way to patch/override existing behavior in the legacy publicWidget registry.
publicWidget.registry.WebsiteSale = CarReservationWidget;
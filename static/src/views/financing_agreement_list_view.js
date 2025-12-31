/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";

export const financingAgreementListView = {
    ...listView,
    buttonTemplate: "nexus_odoo_car_dealer.financing_agreement_list_buttons",
};

registry.category("views").add("financing_agreement_list", financingAgreementListView);

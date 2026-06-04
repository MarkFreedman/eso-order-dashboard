"""Sage 100 Visual Integrator field layouts for SO import.

Field order matches the official Sage file layout document (filelayout SO.docx).
Header: 110 standard fields + 2 UDFs (OrderSource, DepositPaymentType).
Detail: 74 standard fields.
"""

# SO_SalesOrderHeader — 110 fields in Sage order, plus 2 UDFs appended
HEADER_FIELDS = (
    "SalesOrderNo",                # 1
    "OrderDate",                   # 2
    "OrderType",                   # 3
    "OrderStatus",                 # 4
    "MasterRepeatingOrderNo",      # 5
    "ShipExpireDate",              # 6
    "ARDivisionNo",                # 7
    "CustomerNo",                  # 8
    "BillToDivisionNo",            # 9
    "BillToCustomerNo",            # 10
    "BillToName",                  # 11
    "BillToAddress1",              # 12
    "BillToAddress2",              # 13
    "BillToAddress3",              # 14
    "BillToCity",                  # 15
    "BillToState",                 # 16
    "BillToZipCode",               # 17
    "BillToCountryCode",           # 18
    "ShipToCode",                  # 19
    "ShipToName",                  # 20
    "ShipToAddress1",              # 21
    "ShipToAddress2",              # 22
    "ShipToAddress3",              # 23
    "ShipToCity",                  # 24
    "ShipToState",                 # 25
    "ShipToZipCode",               # 26
    "ShipToCountryCode",           # 27
    "ShipVia",                     # 28
    "ShipZone",                    # 29
    "ShipZoneActual",              # 30
    "ShipWeight",                  # 31
    "CustomerPONo",                # 32
    "FOB",                         # 33
    "WarehouseCode",               # 34
    "ConfirmTo",                   # 35
    "Comment",                     # 36
    "TermsCode",                   # 37
    "TaxSchedule",                 # 38
    "TaxExemptNo",                 # 39
    "InvalidTaxCalc",              # 40
    "PrintSalesOrders",            # 41
    "SalesOrderPrinted",           # 42
    "PrintPickingSheets",          # 43
    "PickingSheetPrinted",         # 44
    "LastInvoiceOrderDate",        # 45
    "LastInvoiceOrderNo",          # 46
    "CurrentInvoiceNo",            # 47
    "CheckNoForDeposit",           # 48
    "CycleCode",                   # 49
    "FaxNo",                       # 50
    "BatchFax",                    # 51
    "BatchEmail",                  # 52
    "EmailAddress",                # 53
    "FreightCalculationMethod",    # 54
    "LotSerialLinesExist",         # 55
    "SalespersonDivisionNo",       # 56
    "SalespersonNo",               # 57
    "SplitCommissions",            # 58
    "SalespersonDivisionNo2",      # 59
    "SalespersonNo2",              # 60
    "SalespersonDivisionNo3",      # 61
    "SalespersonNo3",              # 62
    "SalespersonDivisionNo4",      # 63
    "SalespersonNo4",              # 64
    "SalespersonDivisionNo5",      # 65
    "SalespersonNo5",              # 66
    "EBMUserType",                 # 67
    "EBMSubmissionType",           # 68
    "EBMUserIDSubmittingThisOrder", # 69
    "PaymentType",                 # 70
    "OtherPaymentTypeRefNo",       # 71
    "PaymentTypeCategory",         # 72
    "PayBalance",                  # 73
    "CancelReasonCode",            # 74
    "RMANo",                       # 75
    "JobNo",                       # 76
    "ResidentialAddress",          # 77
    "CRMUserID",                   # 78
    "CRMPersonID",                 # 79
    "CRMOpportunityID",            # 80
    "CRMCompanyID",                # 81
    "CRMProspectID",               # 82
    "PromotedDate",                # 83
    "TelephoneNo",                 # 84
    "TelephoneExt",                # 85
    "TelephoneType",               # 86
    "TaxableSubjectToDiscount",    # 87
    "NonTaxableSubjectToDiscount", # 88
    "TaxSubjToDiscPrcntOfTotSubjTo", # 89
    "DiscountRate",                # 90
    "DiscountAmt",                 # 91
    "TaxableAmt",                  # 92
    "NonTaxableAmt",               # 93
    "SalesTaxAmt",                 # 94
    "Weight",                      # 95
    "FreightAmt",                  # 96
    "DepositAmt",                  # 97
    "CommissionRate",              # 98
    "SplitCommRate2",              # 99
    "SplitCommRate3",              # 100
    "SplitCommRate4",              # 101
    "SplitCommRate5",              # 102
    "NumberOfShippingLabels",      # 103
    "LastNoOfShippingLabels",      # 104
    "DateCreated",                 # 105
    "TimeCreated",                 # 106
    "UserCreatedKey",              # 107
    "DateUpdated",                 # 108
    "TimeUpdated",                 # 109
    "UserUpdatedKey",              # 110
    # UDFs appended after standard fields
    "UDF_OrderSource",             # 111
    "UDF_DepositPaymentType",      # 112
)

# SO_SalesOrderDetail — 74 fields in Sage order
DETAIL_FIELDS = (
    "SalesOrderNo",                # 1
    "LineKey",                     # 2
    "LineSeqNo",                   # 3
    "ItemCode",                    # 4
    "ItemType",                    # 5
    "ItemCodeDesc",                # 6
    "ExtendedDescriptionKey",      # 7
    "Discount",                    # 8
    "Commissionable",              # 9
    "SubjectToExemption",          # 10
    "WarehouseCode",               # 11
    "Valuation",                   # 12
    "PriceLevel",                  # 13
    "MasterOrderLineKey",          # 14
    "UnitOfMeasure",               # 15
    "DropShip",                    # 16
    "LotSerialFullyDistributed",   # 17
    "PrintDropShipment",           # 18
    "SalesKitLineKey",             # 19
    "CostOfGoodsSoldAcctKey",      # 20
    "SalesAcctKey",                # 21
    "PriceOverridden",             # 22
    "ExplodedKitItem",             # 23
    "StandardKitBill",             # 24
    "Revision",                    # 25
    "BillOption1",                 # 26
    "BillOption2",                 # 27
    "BillOption3",                 # 28
    "BillOption4",                 # 29
    "BillOption5",                 # 30
    "BillOption6",                 # 31
    "BillOption7",                 # 32
    "BillOption8",                 # 33
    "BillOption9",                 # 34
    "BackorderKitCompLine",        # 35
    "SkipPrintCompLine",           # 36
    "PromiseDate",                 # 37
    "AliasItemNo",                 # 38
    "SOHistoryDetlSeqNo",          # 39
    "TaxClass",                    # 40
    "CustomerAction",              # 41
    "ItemAction",                  # 42
    "WarrantyCode",                # 43
    "ExpirationDate",              # 44
    "ExpirationOverridden",        # 45
    "CostOverridden",              # 46
    "CostCode",                    # 47
    "CostType",                    # 48
    "CommentText",                 # 49
    "APDivisionNo",                # 50
    "VendorNo",                    # 51
    "PurchaseOrderNo",             # 52
    "PurchaseOrderRequiredDate",   # 53
    "CommodityCode",               # 54
    "AlternateTaxIdentifier",      # 55
    "TaxTypeApplied",              # 56
    "NetGrossIndicator",           # 57
    "DebitCreditIndicator",        # 58
    "QuantityOrdered",             # 59
    "QuantityShipped",             # 60
    "QuantityBackordered",         # 61
    "MasterOriginalQty",           # 62
    "MasterQtyBalance",            # 63
    "MasterQtyOrderedToDate",      # 64
    "RepeatingQtyShippedToDate",   # 65
    "UnitPrice",                   # 66
    "UnitCost",                    # 67
    "ExtensionAmt",                # 68
    "UnitOfMeasureConvFactor",     # 69
    "QuantityPerBill",             # 70
    "LineDiscountPercent",         # 71
    "LineWeight",                  # 72
    "TaxAmt",                      # 73
    "TaxRate",                     # 74
)


_FORMULA_PREFIXES = frozenset("=+-@")


def _sanitize_cell(value: str) -> str:
    """Prefix formula-like values with a tab so Excel won't execute them."""
    if value and value[0] in _FORMULA_PREFIXES:
        return "\t" + value
    return value


def dict_to_row(field_tuple, values_dict):
    """Convert a values dict to a CSV row list matching field order.

    Missing keys become empty strings. Sage treats empty fields as
    'use default' during VI import.
    """
    return [_sanitize_cell(str(values_dict.get(f, ""))) for f in field_tuple]

"""Constants shared by the whole dashboard."""
PLANTS = ["BWL-1", "BWL-2", "CWL-1", "CWL-2", "CWL-3", "CWL-4", "EWDL", "NWL", "SWDL", "SZWDL"]
WASH_TYPES = ["Denim", "Acid", "Twill", "Dyeing"]

# Google Sheet tab names (created by the Plan Board file v3)
TAB_ORDERS = "Dashboard_Data"
TAB_DAILY = "Dashboard_Daily"
TAB_HOURLY = "Hourly_Monitor"
TAB_INPUT = "Input_Board"
TAB_OUTPUT = "Output_Board"
TAB_UNIT = "Unit_Master"

C_PLAN = "#C7CBD4"      # plan (grey)
C_ACT = "#14B8A6"       # actual (teal)
C_PURPLE = "#6366F1"
C_AMBER = "#F59E0B"
C_ROSE = "#F43F5E"
C_GREEN = "#22C55E"
C_VIOLET = "#A855F7"
C_PINK = "#EC4899"

NUM_COLS = [
    "Order_Qty", "Total_Sewing_Input", "Total_Wash_Output", "Wash_WIP", "Rewash_WIP", "Total_WIP", "Total_Dry_Output",
    "Wash_Balance", "Sewing_Balance", "Input_Plan_Till_Today", "Output_Plan_Till_Today", "Dry_Plan_Till_Today",
    "Month_Input_Plan", "Month_Output_Plan", "Month_Dry_Plan", "Rewash_Input", "Defect_Pcs", "Today_Input", "Today_Output",
    "Today_Output_Plan", "Today_Input_Plan", "Holding_Days",
]
DATE_COLS = ["CRD", "Plan_Start", "Plan_End", "Last_Input_Date", "Last_Output_Date", "First_Input_Date", "Report_Date"]
TEXT_COLS = ["Order", "Wash_Plant", "Sewing_Unit", "Buyer", "Style", "PO", "Color", "Item", "Wash_Type", "Risk"]

CRISIS_DAYS = 7          # CRD within this many days (or overdue) and balance still open
BEHIND_PCT = 0.80        # output below this share of plan = behind plan

"""
Report Generator

Generates end-of-day reports with sample output.
"""

from datetime import date
from app.event_driven.reporting.daily_ledger import DailyLedger
from app.event_driven.reporting.dual_ledger import DualLedgerReport
from app.core.logger import logger


def generate_sample_report():
    """Generate a sample end-of-day report"""
    ledger = DailyLedger()
    
    # Generate report for today
    report = ledger.generate_end_of_day_report()
    
    print(report)
    
    # Export as JSON
    json_output = ledger.export_json()
    print("\n" + "=" * 80)
    print("JSON Export:")
    print("=" * 80)
    print(json_output)
    
    # Export as CSV
    csv_output = ledger.export_csv()
    print("\n" + "=" * 80)
    print("CSV Export (first 500 chars):")
    print("=" * 80)
    print(csv_output[:500] + "..." if len(csv_output) > 500 else csv_output)


def generate_dual_ledger_report(account_id: str = "HAMMER"):
    """Generate dual-ledger combined report"""
    dual_ledger = DualLedgerReport(account_id=account_id)
    
    # Generate combined report
    report = dual_ledger.generate_combined_report()
    print(report)
    
    # Export as JSON
    json_output = dual_ledger.export_combined_json()
    print("\n" + "=" * 80)
    print("Combined JSON Export:")
    print("=" * 80)
    print(json_output)


def main():
    """Main entry point"""
    import sys
    
    # Check if dual-ledger report requested
    if len(sys.argv) > 1 and sys.argv[1] == "--dual":
        account_id = sys.argv[2] if len(sys.argv) > 2 else "HAMMER"
        generate_dual_ledger_report(account_id)
    else:
        generate_sample_report()


if __name__ == "__main__":
    main()


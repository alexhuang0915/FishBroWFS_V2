#!/usr/bin/env python3
"""
Explain Dictionary Audit Script v2.3

Audits the gate reason explain dictionary for:
1. Completeness - all GateReasonCode enum values have entries
2. Consistency - all entries have required fields with proper formatting
3. Template variable validation - all placeholders are valid
4. Persona support - check persona compatibility
5. Export compatibility - ensure explanations can be exported

Usage:
    python scripts/audit_explain_dictionary.py [--verbose] [--fix]

Outputs:
    - Summary report to stdout
    - Detailed findings to outputs/_dp_evidence/dictionary_audit/
"""

import sys
import os
import re
import json
import argparse
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contracts.portfolio.gate_reason_explain import (
    GATE_REASON_EXPLAIN_DICTIONARY,
    get_gate_reason_explanation,
    get_all_gate_reason_codes,
    DICTIONARY_VERSION,
)
from contracts.portfolio.gate_summary_schemas import GateReasonCode
from contracts.research.explain_persona import ExplainPersona, get_all_personas


class DictionaryAuditor:
    """Audit the explain dictionary for completeness and consistency."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.findings: List[Dict] = []
        self.output_dir = Path("outputs/_dp_evidence/dictionary_audit")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with level."""
        if self.verbose or level in ["ERROR", "WARNING"]:
            print(f"[{level}] {message}")
    
    def add_finding(self, 
                   code: str, 
                   issue: str, 
                   severity: str = "WARNING",
                   recommendation: str = ""):
        """Add a finding to the audit results."""
        self.findings.append({
            "code": code,
            "issue": issue,
            "severity": severity,
            "recommendation": recommendation,
            "timestamp": self._get_timestamp()
        })
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def audit_completeness(self):
        """Check that all GateReasonCode enum values have dictionary entries."""
        self.log("Auditing dictionary completeness...")
        
        # Get all enum values
        enum_codes = {code.value for code in GateReasonCode}
        dict_codes = set(get_all_gate_reason_codes())
        
        # Check for missing entries
        missing = enum_codes - dict_codes
        for code in missing:
            self.add_finding(
                code=code,
                issue=f"Missing dictionary entry for GateReasonCode enum value",
                severity="ERROR",
                recommendation=f"Add entry to GATE_REASON_EXPLAIN_DICTIONARY"
            )
        
        # Check for extra entries (not in enum)
        extra = dict_codes - enum_codes
        for code in extra:
            self.add_finding(
                code=code,
                issue=f"Dictionary entry not in GateReasonCode enum",
                severity="WARNING",
                recommendation=f"Either add to enum or remove from dictionary"
            )
        
        self.log(f"Completeness audit: {len(missing)} missing, {len(extra)} extra entries")
    
    def audit_consistency(self):
        """Check that all dictionary entries have required fields and proper formatting."""
        self.log("Auditing dictionary consistency...")
        
        required_fields = [
            "developer_explanation",
            "business_impact", 
            "recommended_action",
            "severity",
            "audience"
        ]
        
        valid_severities = {"INFO", "WARN", "ERROR"}
        valid_audiences = {"dev", "business", "both"}
        
        for code, entry in GATE_REASON_EXPLAIN_DICTIONARY.items():
            # Check required fields
            for field in required_fields:
                if field not in entry:
                    self.add_finding(
                        code=code,
                        issue=f"Missing required field: {field}",
                        severity="ERROR",
                        recommendation=f"Add {field} field to dictionary entry"
                    )
                elif not entry[field]:
                    self.add_finding(
                        code=code,
                        issue=f"Empty field: {field}",
                        severity="WARNING",
                        recommendation=f"Provide content for {field} field"
                    )
            
            # Check severity validity
            if "severity" in entry and entry["severity"] not in valid_severities:
                self.add_finding(
                    code=code,
                    issue=f"Invalid severity: {entry['severity']}",
                    severity="ERROR",
                    recommendation=f"Severity must be one of: {', '.join(valid_severities)}"
                )
            
            # Check audience validity
            if "audience" in entry and entry["audience"] not in valid_audiences:
                self.add_finding(
                    code=code,
                    issue=f"Invalid audience: {entry['audience']}",
                    severity="ERROR",
                    recommendation=f"Audience must be one of: {', '.join(valid_audiences)}"
                )
            
            # Check explanation length
            if "developer_explanation" in entry:
                explanation = entry["developer_explanation"]
                if len(explanation) < 20:
                    self.add_finding(
                        code=code,
                        issue=f"Developer explanation too short ({len(explanation)} chars)",
                        severity="WARNING",
                        recommendation="Provide more detailed technical explanation"
                    )
                elif len(explanation) > 1000:
                    self.add_finding(
                        code=code,
                        issue=f"Developer explanation too long ({len(explanation)} chars)",
                        severity="WARNING",
                        recommendation="Consider breaking into multiple paragraphs"
                    )
    
    def audit_template_variables(self):
        """Check template variables in explanations."""
        self.log("Auditing template variables...")
        
        # Pattern to find template variables like {variable_name}
        template_pattern = re.compile(r'\{([^}]+)\}')
        
        for code, entry in GATE_REASON_EXPLAIN_DICTIONARY.items():
            for field in ["developer_explanation", "business_impact", "recommended_action"]:
                if field in entry:
                    text = entry[field]
                    variables = template_pattern.findall(text)
                    
                    if variables:
                        self.log(f"  {code}: {field} has variables {variables}", "DEBUG")
                        
                        # Check if variables are used consistently
                        for var in variables:
                            # Simple validation: variable names should be snake_case or lowercase
                            if not re.match(r'^[a-z][a-z0-9_]*$', var):
                                self.add_finding(
                                    code=code,
                                    issue=f"Invalid template variable name: '{var}' in {field}",
                                    severity="WARNING",
                                    recommendation="Use snake_case variable names (lowercase with underscores)"
                                )
    
    def audit_persona_support(self):
        """Check if explanations work with different personas."""
        self.log("Auditing persona support...")
        
        # Check if explanations have persona-appropriate content
        for code, entry in GATE_REASON_EXPLAIN_DICTIONARY.items():
            audience = entry.get("audience", "both")
            
            # Check if audience matches persona needs
            if audience == "dev":
                # Technical persona only
                self.add_finding(
                    code=code,
                    issue="Explanation audience is 'dev' only",
                    severity="INFO",
                    recommendation="Consider adding business impact for non-technical personas"
                )
            elif audience == "business":
                # Business persona only
                self.add_finding(
                    code=code,
                    issue="Explanation audience is 'business' only",
                    severity="INFO",
                    recommendation="Consider adding technical details for engineer personas"
                )
            
            # Check explanation quality for different personas
            dev_explanation = entry.get("developer_explanation", "")
            business_impact = entry.get("business_impact", "")
            
            # For ENGINEER persona, need technical details
            if audience in ["dev", "both"] and len(dev_explanation) < 50:
                self.add_finding(
                    code=code,
                    issue="Developer explanation may be insufficient for ENGINEER persona",
                    severity="WARNING",
                    recommendation="Add more technical details for engineer audience"
                )
            
            # For EXEC/PM personas, need clear business impact
            if audience in ["business", "both"] and len(business_impact) < 30:
                self.add_finding(
                    code=code,
                    issue="Business impact may be insufficient for EXEC/PM personas",
                    severity="WARNING",
                    recommendation="Add clearer business implications for executive audience"
                )
    
    def audit_export_compatibility(self):
        """Check if explanations can be exported properly."""
        self.log("Auditing export compatibility...")
        
        # Test export with sample context variables
        test_context = {
            "job_id": "test_job_123",
            "error_class": "ValueError",
            "error_message": "Test error message",
            "schema_version": "v1",
            "raw_preview": "[truncated]",
            "relpath": "metrics.json",
            "expected_sha256": "abc123...",
            "observed_sha256": "def456...",
            "cycle_path": "A->B->C->A"
        }
        
        for code in get_all_gate_reason_codes():
            try:
                # Test with context variables
                explanation = get_gate_reason_explanation(code, test_context)
                
                # Check if explanation can be JSON serialized
                json.dumps(explanation)
                
                # Check for unsubstituted placeholders
                for field in ["developer_explanation", "business_impact", "recommended_action"]:
                    if field in explanation:
                        text = explanation[field]
                        if "{" in text and "}" in text:
                            # Might have unsubstituted placeholders
                            self.add_finding(
                                code=code,
                                issue=f"Possible unsubstituted placeholder in {field} after context application",
                                severity="WARNING",
                                recommendation="Check template variable names match context keys"
                            )
                
            except Exception as e:
                self.add_finding(
                    code=code,
                    issue=f"Export test failed: {str(e)}",
                    severity="ERROR",
                    recommendation="Fix explanation generation or template variables"
                )
    
    def run_all_audits(self):
        """Run all audit checks."""
        self.log(f"Starting Explain Dictionary Audit v2.3")
        self.log(f"Dictionary Version: {DICTIONARY_VERSION}")
        self.log(f"Total entries: {len(GATE_REASON_EXPLAIN_DICTIONARY)}")
        
        self.audit_completeness()
        self.audit_consistency()
        self.audit_template_variables()
        self.audit_persona_support()
        self.audit_export_compatibility()
        
        self.log(f"Audit complete. Found {len(self.findings)} issues.")
    
    def generate_report(self) -> Dict:
        """Generate audit report."""
        # Categorize findings
        by_severity = {}
        by_code = {}
        
        for finding in self.findings:
            severity = finding["severity"]
            code = finding["code"]
            
            by_severity.setdefault(severity, []).append(finding)
            by_code.setdefault(code, []).append(finding)
        
        # Summary statistics
        total_entries = len(GATE_REASON_EXPLAIN_DICTIONARY)
        error_count = len(by_severity.get("ERROR", []))
        warning_count = len(by_severity.get("WARNING", []))
        info_count = len(by_severity.get("INFO", []))
        
        report = {
            "metadata": {
                "audit_version": "v2.3",
                "dictionary_version": DICTIONARY_VERSION,
                "timestamp": self._get_timestamp(),
                "total_entries": total_entries,
                "findings_count": len(self.findings),
                "error_count": error_count,
                "warning_count": warning_count,
                "info_count": info_count,
            },
            "summary": {
                "status": "PASS" if error_count == 0 else "FAIL",
                "message": f"Found {error_count} errors, {warning_count} warnings, {info_count} info items"
            },
            "findings_by_severity": by_severity,
            "findings_by_code": by_code,
            "all_findings": self.findings
        }
        
        return report
    
    def save_report(self, report: Dict):
        """Save audit report to files."""
        # Save JSON report
        json_path = self.output_dir / "audit_report.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save markdown summary
        md_path = self.output_dir / "audit_summary.md"
        self._save_markdown_report(report, md_path)
        
        # Save findings CSV
        csv_path = self.output_dir / "findings.csv"
        self._save_csv_findings(csv_path)
        
        self.log(f"Reports saved to: {self.output_dir}")
    
    def _save_markdown_report(self, report: Dict, path: Path):
        """Save markdown summary report."""
        metadata = report["metadata"]
        summary = report["summary"]
        
        with open(path, "w") as f:
            f.write("# Explain Dictionary Audit Report v2.3\n\n")
            f.write(f"**Audit Date:** {metadata['timestamp']}\n")
            f.write(f"**Dictionary Version:** {metadata['dictionary_version']}\n")
            f.write(f"**Total Entries:** {metadata['total_entries']}\n")
            f.write(f"**Status:** **{summary['status']}**\n")
            f.write(f"**Message:** {summary['message']}\n\n")
            
            f.write("## Findings Summary\n\n")
            f.write(f"- ❌ **Errors:** {metadata['error_count']}\n")
            f.write(f"- ⚠️ **Warnings:** {metadata['warning_count']}\n")
            f.write(f"- ℹ️ **Info:** {metadata['info_count']}\n\n")
            
            if metadata['error_count'] > 0:
                f.write("## Critical Issues (ERROR)\n\n")
                for finding in report['findings_by_severity'].get('ERROR', []):
                    f.write(f"### {finding['code']}\n")
                    f.write(f"- **Issue:** {finding['issue']}\n")
                    f.write(f"- **Recommendation:** {finding['recommendation']}\n\n")
            
            if metadata['warning_count'] > 0:
                f.write("## Warnings\n\n")
                for finding in report['findings_by_severity'].get('WARNING', []):
                    f.write(f"### {finding['code']}\n")
                    f.write(f"- **Issue:** {finding['issue']}\n")
                    f.write(f"- **Recommendation:** {finding['recommendation']}\n\n")
    
    def _save_csv_findings(self, path: Path):
        """Save findings as CSV."""
        import csv
        
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Code", "Severity", "Issue", "Recommendation", "Timestamp"])
            
            for finding in self.findings:
                writer.writerow([
                    finding["code"],
                    finding["severity"],
                    finding["issue"],
                    finding["recommendation"],
                    finding["timestamp"]
                ])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Audit Explain Dictionary v2.3")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues (not implemented)")
    parser.add_argument("--output-dir", default="outputs/_dp_evidence/dictionary_audit", 
                       help="Output directory for reports")
    
    args = parser.parse_args()
    
    # Create auditor
    auditor = DictionaryAuditor(verbose=args.verbose)
    
    try:
        # Run audits
        auditor.run_all_audits()
        
        # Generate report
        report = auditor.generate_report()
        
        # Save reports
        auditor.save_report(report)
        
        # Print summary
        print("\n" + "="*60)
        print("EXPLAIN DICTIONARY AUDIT SUMMARY")
        print("="*60)
        print(f"Dictionary Version: {report['metadata']['dictionary_version']}")
        print(f"Total Entries: {report['metadata']['total_entries']}")
        print(f"Findings: {report['metadata']['findings_count']} total")
        print(f"  ❌ Errors: {report['metadata']['error_count']}")
        print(f"  ⚠️  Warnings: {report['metadata']['warning_count']}")
        print(f"  ℹ️  Info: {report['metadata']['info_count']}")
        print(f"Status: {report['summary']['status']}")
        print(f"Message: {report['summary']['message']}")
        print("="*60)
        
        # Exit with error code if critical issues found
        if report['metadata']['error_count'] > 0:
            print("\n❌ Critical issues found. Please fix before deployment.")
            sys.exit(1)
        elif report['metadata']['warning_count'] > 0:
            print("\n⚠️  Warnings found. Review before deployment.")
            sys.exit(0)
        else:
            print("\n✅ All checks passed. Dictionary is ready for v2.3 deployment.")
            sys.exit(0)
            
    except Exception as e:
        print(f"\n❌ Audit failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
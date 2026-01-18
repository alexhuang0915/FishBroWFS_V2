#!/usr/bin/env python3
"""
Explain Quality Audit Script v2.4

Audits explanation quality for v2.4 persona tone consistency:
1. Persona tone rule completeness and validity
2. Quality normalizer deterministic behavior
3. Semantic preservation across personas
4. Performance characteristics
5. Integration with research narrative builder

Usage:
    python scripts/audit_explain_quality_v24.py [--verbose] [--sample-texts]

Outputs:
    - Summary report to stdout
    - Detailed findings to outputs/_dp_evidence/ui_explain_v24/quality_audit/
"""

import sys
import os
import json
import time
import argparse
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contracts.research.explain_persona import ExplainPersona, get_all_personas
from contracts.research.explain_persona_tone import (
    PersonaToneRule,
    PERSONA_TONE_RULES,
    get_persona_tone_rule,
    validate_explanation_tone,
    get_tone_guidelines,
)
from src.core.explain_quality_normalizer import (
    ExplainQualityNormalizer,
    normalize_explanation_for_persona,
    get_quality_normalizer,
)
from src.core.research.research_narrative_builder import ResearchNarrativeBuilder


class QualityAuditor:
    """Audit explanation quality for v2.4 persona tone consistency."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.findings: List[Dict] = []
        self.output_dir = Path("outputs/_dp_evidence/ui_explain_v24/quality_audit")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Sample texts for testing
        self.sample_texts = [
            # Technical text
            "The system encountered a ValueError when parsing the JSON schema. "
            "The error occurred at line 42 where the 'timestamp' field was expected "
            "to be an ISO 8601 string but received null instead.",
            
            # Business text
            "This initiative will deliver significant ROI by Q3 2024. "
            "Stakeholder value is projected to increase by 15% based on current metrics.",
            
            # Mixed text
            "Technical debt in the data pipeline is impacting delivery timelines. "
            "We need to refactor the ingestion module to improve performance.",
            
            # Short text
            "System ready for execution.",
            
            # Long text
            "This is a comprehensive explanation that covers multiple aspects of "
            "the research pipeline including data validation, strategy execution, "
            "outcome analysis, and decision making processes that need to be "
            "considered for optimal portfolio construction and risk management.",
        ]
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with level."""
        if self.verbose or level in ["ERROR", "WARNING"]:
            print(f"[{level}] {message}")
    
    def add_finding(self, 
                   category: str,
                   issue: str, 
                   severity: str = "WARNING",
                   recommendation: str = "",
                   details: Optional[Dict] = None):
        """Add a finding to the audit results."""
        self.findings.append({
            "category": category,
            "issue": issue,
            "severity": severity,
            "recommendation": recommendation,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        })
    
    def audit_persona_tone_rules(self):
        """Audit persona tone rules completeness and validity."""
        self.log("Auditing persona tone rules...")
        
        # Check all personas have rules
        all_personas = set(get_all_personas())
        rule_personas = set(PERSONA_TONE_RULES.keys())
        
        missing = all_personas - rule_personas
        for persona in missing:
            self.add_finding(
                category="persona_tone_rules",
                issue=f"Missing tone rule for persona: {persona.value}",
                severity="ERROR",
                recommendation=f"Add PersonaToneRule for {persona.value} to PERSONA_TONE_RULES"
            )
        
        extra = rule_personas - all_personas
        for persona in extra:
            self.add_finding(
                category="persona_tone_rules",
                issue=f"Extra tone rule for unknown persona: {persona}",
                severity="WARNING",
                recommendation=f"Remove or fix persona reference"
            )
        
        # Validate each rule
        for persona, rule in PERSONA_TONE_RULES.items():
            try:
                # Validate rule structure
                rule.model_validate(rule.model_dump())
                
                # Check rule constraints
                if rule.min_sentence_length <= 0:
                    self.add_finding(
                        category="persona_tone_rules",
                        issue=f"Invalid min_sentence_length ({rule.min_sentence_length}) for {persona.value}",
                        severity="ERROR",
                        recommendation="min_sentence_length must be > 0",
                        details={"persona": persona.value, "value": rule.min_sentence_length}
                    )
                
                if rule.max_sentence_length < rule.min_sentence_length:
                    self.add_finding(
                        category="persona_tone_rules",
                        issue=f"max_sentence_length ({rule.max_sentence_length}) < min_sentence_length ({rule.min_sentence_length}) for {persona.value}",
                        severity="ERROR",
                        recommendation="max_sentence_length must be >= min_sentence_length",
                        details={
                            "persona": persona.value,
                            "min": rule.min_sentence_length,
                            "max": rule.max_sentence_length
                        }
                    )
                
                if rule.max_sentences_per_paragraph <= 0:
                    self.add_finding(
                        category="persona_tone_rules",
                        issue=f"Invalid max_sentences_per_paragraph ({rule.max_sentences_per_paragraph}) for {persona.value}",
                        severity="ERROR",
                        recommendation="max_sentences_per_paragraph must be > 0",
                        details={"persona": persona.value, "value": rule.max_sentences_per_paragraph}
                    )
                
                # Check style guidelines not empty
                if not rule.style_guidelines or not rule.style_guidelines.strip():
                    self.add_finding(
                        category="persona_tone_rules",
                        issue=f"Empty style_guidelines for {persona.value}",
                        severity="WARNING",
                        recommendation="Provide meaningful style guidelines",
                        details={"persona": persona.value}
                    )
                
            except Exception as e:
                self.add_finding(
                    category="persona_tone_rules",
                    issue=f"Invalid tone rule for {persona.value}: {str(e)}",
                    severity="ERROR",
                    recommendation="Fix PersonaToneRule definition",
                    details={"persona": persona.value, "error": str(e)}
                )
        
        self.log(f"Persona tone rules audit: {len(missing)} missing, {len(extra)} extra, {len(PERSONA_TONE_RULES)} total")
    
    def audit_quality_normalizer_deterministic(self):
        """Audit that quality normalizer is deterministic."""
        self.log("Auditing quality normalizer deterministic behavior...")
        
        normalizer = get_quality_normalizer()
        
        # Test with sample texts
        for i, text in enumerate(self.sample_texts):
            for persona in ExplainPersona:
                # First normalization
                result1 = normalizer.normalize_for_persona(
                    text=text,
                    target_persona=persona
                )
                
                # Second normalization (should be identical)
                result2 = normalizer.normalize_for_persona(
                    text=text,
                    target_persona=persona
                )
                
                # Check determinism
                if result1.normalized_text != result2.normalized_text:
                    self.add_finding(
                        category="quality_normalizer",
                        issue=f"Non-deterministic normalization for {persona.value} (sample {i})",
                        severity="ERROR",
                        recommendation="Ensure normalization is deterministic (same input → same output)",
                        details={
                            "persona": persona.value,
                            "sample_index": i,
                            "text_length": len(text),
                            "result1": result1.normalized_text[:100] + "..." if len(result1.normalized_text) > 100 else result1.normalized_text,
                            "result2": result2.normalized_text[:100] + "..." if len(result2.normalized_text) > 100 else result2.normalized_text
                        }
                    )
                
                # Check that NormalizationResult is frozen
                try:
                    result1.original_text = "modified"
                    self.add_finding(
                        category="quality_normalizer",
                        issue=f"NormalizationResult not frozen for {persona.value}",
                        severity="ERROR",
                        recommendation="Add @dataclass(frozen=True) to NormalizationResult",
                        details={"persona": persona.value}
                    )
                except (AttributeError, TypeError, ValueError):
                    # Expected - result should be frozen
                    pass
        
        self.log(f"Determinism audit: tested {len(self.sample_texts)} texts across {len(ExplainPersona)} personas")
    
    def audit_semantic_preservation(self):
        """Audit that normalization preserves semantic meaning."""
        self.log("Auditing semantic preservation...")
        
        normalizer = get_quality_normalizer()
        
        # Test texts that should preserve meaning
        test_cases = [
            {
                "text": "The system is ready for research execution.",
                "expected_keywords": ["system", "ready", "research", "execution"]
            },
            {
                "text": "Data validation passed all quality gates.",
                "expected_keywords": ["data", "validation", "passed", "quality", "gates"]
            },
            {
                "text": "Portfolio construction requires candidate strategies.",
                "expected_keywords": ["portfolio", "construction", "requires", "candidate", "strategies"]
            }
        ]
        
        for test_case in test_cases:
            text = test_case["text"]
            expected_keywords = test_case["expected_keywords"]
            
            for persona in ExplainPersona:
                result = normalizer.normalize_for_persona(
                    text=text,
                    target_persona=persona
                )
                
                # Check that key semantic elements are preserved
                normalized_lower = result.normalized_text.lower()
                missing_keywords = []
                
                for keyword in expected_keywords:
                    if keyword.lower() not in normalized_lower:
                        missing_keywords.append(keyword)
                
                if missing_keywords:
                    self.add_finding(
                        category="semantic_preservation",
                        issue=f"Missing semantic keywords after normalization for {persona.value}: {missing_keywords}",
                        severity="WARNING",
                        recommendation="Ensure key semantic elements are preserved during normalization",
                        details={
                            "persona": persona.value,
                            "original_text": text,
                            "normalized_text": result.normalized_text,
                            "missing_keywords": missing_keywords,
                            "expected_keywords": expected_keywords
                        }
                    )
        
        self.log(f"Semantic preservation audit: tested {len(test_cases)} cases across {len(ExplainPersona)} personas")
    
    def audit_performance(self):
        """Audit normalization performance."""
        self.log("Auditing normalization performance...")
        
        normalizer = get_quality_normalizer()
        
        # Performance test
        test_text = "A typical explanation of moderate length for performance testing."
        
        # Single normalization timing
        start_time = time.perf_counter()
        result = normalizer.normalize_for_persona(
            text=test_text,
            target_persona=ExplainPersona.TRADER
        )
        single_duration_ms = (time.perf_counter() - start_time) * 1000
        
        if single_duration_ms > 10:  # 10ms threshold
            self.add_finding(
                category="performance",
                issue=f"Single normalization too slow: {single_duration_ms:.2f}ms",
                severity="WARNING",
                recommendation="Optimize normalization algorithms for speed",
                details={
                    "duration_ms": single_duration_ms,
                    "threshold_ms": 10,
                    "text_length": len(test_text)
                }
            )
        
        # Batch normalization timing
        batch_size = 100
        batch_texts = [test_text] * batch_size
        
        start_time = time.perf_counter()
        results = normalizer.batch_normalize(
            texts=batch_texts,
            target_persona=ExplainPersona.QA
        )
        batch_duration_ms = (time.perf_counter() - start_time) * 1000
        avg_per_text = batch_duration_ms / batch_size
        
        if avg_per_text > 5:  # 5ms per text threshold
            self.add_finding(
                category="performance",
                issue=f"Batch normalization too slow: {avg_per_text:.2f}ms per text",
                severity="WARNING",
                recommendation="Optimize batch normalization",
                details={
                    "batch_size": batch_size,
                    "total_duration_ms": batch_duration_ms,
                    "avg_per_text_ms": avg_per_text,
                    "threshold_ms": 5
                }
            )
        
        self.log(f"Performance audit: single={single_duration_ms:.2f}ms, batch={avg_per_text:.2f}ms per text")
    
    def audit_narrative_builder_integration(self):
        """Audit integration with research narrative builder."""
        self.log("Auditing narrative builder integration...")
        
        try:
            builder = ResearchNarrativeBuilder()
            builder_info = builder.get_builder_info()
            
            # Check builder version
            if builder_info.get("builder_version") != "v2.4.0":
                self.add_finding(
                    category="integration",
                    issue=f"ResearchNarrativeBuilder version mismatch: {builder_info.get('builder_version')}",
                    severity="ERROR",
                    recommendation="Update ResearchNarrativeBuilder version to v2.4.0",
                    details={"current_version": builder_info.get("builder_version")}
                )
            
            # Check persona support
            supported_personas = builder_info.get("supported_personas", [])
            all_personas = [p.value for p in ExplainPersona]
            
            missing_personas = set(all_personas) - set(supported_personas)
            for persona in missing_personas:
                self.add_finding(
                    category="integration",
                    issue=f"ResearchNarrativeBuilder missing persona support: {persona}",
                    severity="ERROR",
                    recommendation="Ensure all personas are supported",
                    details={"missing_persona": persona}
                )
            
            # Check that builder uses quality normalizer
            # This is a structural check - we can't easily test runtime behavior
            self.log("Integration audit: builder version check complete")
            
        except Exception as e:
            self.add_finding(
                category="integration",
                issue=f"Failed to audit narrative builder integration: {str(e)}",
                severity="ERROR",
                recommendation="Fix ResearchNarrativeBuilder import or initialization",
                details={"error": str(e)}
            )
    
    def audit_tone_validation(self):
        """Audit tone validation functionality."""
        self.log("Auditing tone validation...")
        
        # Test validation with sample texts
        for i, text in enumerate(self.sample_texts):
            for persona in ExplainPersona:
                issues = validate_explanation_tone(
                    text=text,
                    persona=persona,
                    check_length=True,
                    check_terms=True
                )
                
                # Check that validation returns list of strings
                if not isinstance(issues, list):
                    self.add_finding(
                        category="tone_validation",
                        issue=f"validate_explanation_tone returned non-list for {persona.value} (sample {i})",
                        severity="ERROR",
                        recommendation="validate_explanation_tone should return List[str]",
                        details={
                            "persona": persona.value,
                            "sample_index": i,
                            "return_type": type(issues).__name__
                        }
                    )
                    continue
                
                # Check each issue is a string
                for issue in issues:
                    if not isinstance(issue, str):
                        self.add_finding(
                            category="tone_validation",
                            issue=f"validate_explanation_tone returned non-string issue for {persona.value}",
                            severity="ERROR",
                            recommendation="All validation issues should be strings",
                            details={
                                "persona": persona.value,
                                "sample_index": i,
                                "issue_type": type(issue).__name__
                            }
                        )
        
        self.log(f"Tone validation audit: tested {len(self.sample_texts)} texts across {len(ExplainPersona)} personas")
    
    def run_all_audits(self):
        """Run all audit checks."""
        self.log(f"Starting Explain Quality Audit v2.4")
        self.log(f"Timestamp: {datetime.now().isoformat()}")
        
        self.audit_persona_tone_rules()
        self.audit_quality_normalizer_deterministic()
        self.audit_semantic_preservation()
        self.audit_performance()
        self.audit_narrative_builder_integration()
        self.audit_tone_validation()
        
        self.log(f"Audit complete. Found {len(self.findings)} issues.")
    
    def generate_report(self) -> Dict:
        """Generate audit report."""
        # Categorize findings
        by_category = {}
        by_severity = {}
        
        for finding in self.findings:
            category = finding["category"]
            severity = finding["severity"]
            
            by_category.setdefault(category, []).append(finding)
            by_severity.setdefault(severity, []).append(finding)
        
        # Summary statistics
        error_count = len(by_severity.get("ERROR", []))
        warning_count = len(by_severity.get("WARNING", []))
        info_count = len(by_severity.get("INFO", []))
        
        report = {
            "metadata": {
                "audit_version": "v2.4",
                "timestamp": datetime.now().isoformat(),
                "persona_count": len(ExplainPersona),
                "tone_rule_count": len(PERSONA_TONE_RULES),
                "findings_count": len(self.findings),
                "error_count": error_count,
                "warning_count": warning_count,
                "info_count": info_count,
            },
            "summary": {
                "status": "PASS" if error_count == 0 else "FAIL",
                "message": f"Found {error_count} errors, {warning_count} warnings, {info_count} info items"
            },
            "findings_by_category": by_category,
            "findings_by_severity": by_severity,
            "all_findings": self.findings
        }
        
        return report
    
    def save_report(self, report: Dict):
        """Save audit report to files."""
        # Save JSON report
        json_path = self.output_dir / "quality_audit_report.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save markdown summary
        md_path = self.output_dir / "quality_audit_summary.md"
        self._save_markdown_report(report, md_path)
        
        self.log(f"Reports saved to: {self.output_dir}")
    
    def _save_markdown_report(self, report: Dict, path: Path):
        """Save markdown summary report."""
        metadata = report["metadata"]
        summary = report["summary"]
        
        with open(path, "w") as f:
            f.write("# Explain Quality Audit Report v2.4\n\n")
            f.write(f"**Audit Date:** {metadata['timestamp']}\n")
            f.write(f"**Persona Count:** {metadata['persona_count']}\n")
            f.write(f"**Tone Rule Count:** {metadata['tone_rule_count']}\n")
            f.write(f"**Status:** **{summary['status']}**\n")
            f.write(f"**Message:** {summary['message']}\n\n")
            
            f.write("## Findings Summary\n\n")
            f.write(f"- ❌ **Errors:** {metadata['error_count']}\n")
            f.write(f"- ⚠️ **Warnings:** {metadata['warning_count']}\n")
            f.write(f"- ℹ️ **Info:** {metadata['info_count']}\n\n")
            
            # Findings by category
            f.write("## Findings by Category\n\n")
            for category, findings in report['findings_by_category'].items():
                f.write(f"### {category}\n")
                f.write(f"**Count:** {len(findings)}\n\n")
                
                for finding in findings[:5]:  # Show first 5
                    severity_icon = "❌" if finding['severity'] == "ERROR" else "⚠️" if finding['severity'] == "WARNING" else "ℹ️"
                    f.write(f"{severity_icon} **{finding['severity']}**: {finding['issue']}\n")
                    if finding.get('recommendation'):
                        f.write(f"  *Recommendation:* {finding['recommendation']}\n")
                if len(findings) > 5:
                    f.write(f"... and {len(findings) - 5} more\n")
                f.write("\n")
            
            if metadata['error_count'] > 0:
                f.write("## Critical Issues (ERROR)\n\n")
                for finding in report['findings_by_severity'].get('ERROR', []):
                    f.write(f"### {finding['category']} - {finding.get('timestamp', '')}\n")
                    f.write(f"- **Issue:** {finding['issue']}\n")
                    f.write(f"- **Recommendation:** {finding['recommendation']}\n")
                    if finding.get('details'):
                        f.write(f"- **Details:** {json.dumps(finding['details'], indent=2)}\n")
                    f.write("\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Audit Explain Quality v2.4")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--sample-texts", action="store_true", help="Use additional sample texts")
    parser.add_argument("--output-dir", default="outputs/_dp_evidence/ui_explain_v24/quality_audit",
                       help="Output directory for reports")
    
    args = parser.parse_args()
    
    # Create auditor
    auditor = QualityAuditor(verbose=args.verbose)
    
    try:
        # Run audits
        auditor.run_all_audits()
        
        # Generate report
        report = auditor.generate_report()
        
        # Save reports
        auditor.save_report(report)
        
        # Print summary
        print("\n" + "="*60)
        print("EXPLAIN QUALITY AUDIT SUMMARY v2.4")
        print("="*60)
        print(f"Persona Count: {report['metadata']['persona_count']}")
        print(f"Tone Rule Count: {report['metadata']['tone_rule_count']}")
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
            print("\n✅ All checks passed. Explain quality v2.4 is ready.")
            sys.exit(0)
            
    except Exception as e:
        print(f"\n❌ Audit failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
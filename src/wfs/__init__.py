"""
WFS (Walk-Forward Search) modules for Red-Team hardened strategy research.
"""

from wfs.evaluation import (
    RawMetrics,
    Scores,
    EvaluationResult,
    compute_hard_gates,
    compute_scores,
    compute_total,
    grade_from_total,
    evaluate,
    create_test_raw_metrics
)

from wfs.evaluation_enhanced import (
    EnhancedRawMetrics,
    EnhancedEvaluationResult,
    evaluate_enhanced,
    evaluate_with_mode_b,
    create_test_enhanced_raw_metrics
)

from wfs.scoring_guards import (
    ScoringGuardConfig,
    compute_trade_multiplier,
    compute_min_edge_gate,
    compute_final_score,
    compute_robust_stats,
    detect_bimodality_cluster,
    apply_scoring_guards,
    score_with_guards,
    DEFAULT_CONFIG
)

from wfs.tsr_calibration import (
    CalibrationMethod,
    TSRCalibrationConfig,
    AnchorPoint,
    calibrate_anchor_params,
    select_mode_b_anchors,
    compute_signal_rate,
    create_mode_b_structure_filter,
    DEFAULT_CALIBRATION_CONFIG
)

from wfs.mode_b_pipeline import (
    ModeBConfig,
    ParameterSet,
    EvaluationResult as ModeBEvaluationResult,
    ModeBPipeline,
    create_mode_b_pipeline
)

from wfs.governance_triggers import (
    GovernancePolicy,
    GovernanceTrigger,
    load_policy_from_yaml,
    create_delta_report,
    enforce_governance,
    DEFAULT_POLICY
)

from wfs.red_team_integration import (
    RedTeamConfig,
    RedTeamHardenedWFS,
    create_red_team_wfs
)

__all__ = [
    # Base Evaluation
    'RawMetrics', 'Scores', 'EvaluationResult',
    'compute_hard_gates', 'compute_scores', 'compute_total',
    'grade_from_total', 'evaluate', 'create_test_raw_metrics',
    
    # Enhanced Evaluation
    'EnhancedRawMetrics', 'EnhancedEvaluationResult',
    'evaluate_enhanced', 'evaluate_with_mode_b',
    'create_test_enhanced_raw_metrics',
    
    # Scoring Guards
    'ScoringGuardConfig', 'compute_trade_multiplier',
    'compute_min_edge_gate', 'compute_final_score',
    'compute_robust_stats', 'detect_bimodality_cluster',
    'apply_scoring_guards', 'score_with_guards', 'DEFAULT_CONFIG',
    
    # TSR Calibration
    'CalibrationMethod', 'TSRCalibrationConfig', 'AnchorPoint',
    'calibrate_anchor_params', 'select_mode_b_anchors',
    'compute_signal_rate', 'create_mode_b_structure_filter',
    'DEFAULT_CALIBRATION_CONFIG',
    
    # Mode B Pipeline
    'ModeBConfig', 'ParameterSet', 'ModeBEvaluationResult',
    'ModeBPipeline', 'create_mode_b_pipeline',
    
    # Governance Triggers
    'GovernancePolicy', 'GovernanceTrigger', 'load_policy_from_yaml',
    'create_delta_report', 'enforce_governance', 'DEFAULT_POLICY',
    
    # Red-Team Integration
    'RedTeamConfig', 'RedTeamHardenedWFS', 'create_red_team_wfs'
]
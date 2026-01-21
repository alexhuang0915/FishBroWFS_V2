# UI Explain v2.4 - Discovery Summary

## 1. Explain Rendering Pipeline Discovery

### A) Core Components Found

**1. ExplainPersona Enum** (`src/contracts/research/explain_persona.py`)
- 5 personas: TRADER, ENGINEER, QA, PM, EXEC
- Each has metadata: display_name, description, icon, technical_level, content_focus
- SSOT for persona definitions

**2. ResearchNarrativeBuilder** (`src/core/research/research_narrative_builder.py`)
- Pure function converting ResearchFlowState → ResearchNarrativeV1
- Persona-aware content generation in:
  - `_build_why_explanation()` - why text (≤400 chars)
  - `_build_developer_view()` - technical view (≤800 chars)  
  - `_build_business_view()` - business view (≤800 chars)
- Length constraints enforced via truncation
- Persona-specific content defined in hardcoded dictionaries per stage

**3. GateReasonExplain Dictionary** (`src/contracts/portfolio/gate_reason_explain.py`)
- Centralized explanation dictionary for gate reason codes
- Provides developer_explanation, business_impact, recommended_action
- Template variable support with context_vars
- Used by narrative builder via `get_gate_reason_explanation()`

**4. ExplainExportService** (`src/gui/services/explain_export_service.py`)
- Persona-aware export service (JSON, Markdown, CSV)
- Batch export support with persona matching
- Includes persona_context metadata

**5. ExplainHubTabs UI** (`src/gui/desktop/widgets/explain_hub_tabs.py`)
- UI component with persona selector
- Calls `get_stage_narrative()` with current persona

### B) Current Persona Implementation Patterns

**1. Content Generation Approach:**
- Hardcoded dictionaries per stage with persona-specific strings
- Example: `success_messages[ResearchStage.DATA_READINESS][ExplainPersona.TRADER]`
- Blocked states use dictionary explanations with persona-specific suffixes

**2. Tone/Quality Issues Identified:**
- No centralized tone rules or quality guidelines
- Persona-specific content is ad-hoc (hardcoded strings)
- No validation of persona-appropriate language
- No consistency checks across similar explanations
- No measurement of explanation quality

**3. Length Constraints:**
- Headline: ≤120 chars
- Why: ≤400 chars  
- Developer/Business views: ≤800 chars
- Enforced via truncation (`[:117] + "..."`)

### C) Integration Points for v2.4

**Primary Integration Target:**
- `ResearchNarrativeBuilder._build_why_explanation()`
- `ResearchNarrativeBuilder._build_developer_view()`
- `ResearchNarrativeBuilder._build_business_view()`

**Secondary Integration Points:**
- `ExplainExportService._build_export_data()` - for persona_context
- `ExplainHubTabs` UI - for persona selection feedback

## 2. Persona Tone Requirements Analysis

### A) Current Persona Characteristics (from metadata):

1. **TRADER** (medium technical)
   - Focus: returns, risk, execution, portfolio
   - Content: concise, actionable insights with trade implications

2. **ENGINEER** (high technical)  
   - Focus: implementation, debugging, architecture, data
   - Content: technical specifications, error analysis, system architecture

3. **QA** (medium_high technical)
   - Focus: testing, validation, reproducibility, quality
   - Content: verification steps, test results, quality metrics

4. **PM** (low_medium technical)
   - Focus: business_value, user_impact, roadmap, prioritization
   - Content: business implications, user stories, ROI analysis

5. **EXEC** (low technical)
   - Focus: strategy, financials, risk, summary
   - Content: executive summaries, key metrics, strategic recommendations

### B) Tone Rule Gaps:
- No sentence length guidelines per persona
- No vocabulary restrictions (technical jargon vs business terms)
- No consistency enforcement
- No quality measurement

## 3. v2.4 Implementation Strategy

### A) Persona Tone Contract (Step 2)
- Create frozen mapping of persona → tone rules
- Rules: sentence length ranges, allowed/forbidden terms, style guidelines
- SSOT for persona tone expectations

### B) Quality Normalizer (Step 3)
- Service to adjust explanation tone for different personas
- Deterministic transformations preserving meaning
- Integration into narrative builder render path

### C) Consistency Tests (Step 5)
- Semantic snapshots (not full-text)
- Test: same reason_code + same persona → same output
- Cross-persona consistency checks

### D) Quality Report Script (Step 6)
- Lightweight measurement without ML
- Metrics: sentence count, keyword presence, violations
- Report format for visibility

## 4. Key Files for Implementation

**New Files:**
1. `src/contracts/explain/explain_persona_tone.py` - Persona tone contract
2. `src/core/explain/explain_quality_normalizer.py` - Quality normalizer service
3. `scripts/explain_quality_report.py` - Quality measurement script

**Modified Files:**
1. `src/core/research/research_narrative_builder.py` - Integrate normalizer
2. `tests/core/research/test_research_narrative_v21.py` - Add consistency tests
3. `Makefile` - Add quality report target

## 5. Discovery Conclusion

**Current State:** v2.3 persona support is structurally complete but lacks quality controls.

**v2.4 Opportunity:** Add persona tone guidelines, quality normalization, consistency checks, and measurement.

**Implementation Order:**
1. Persona Tone Contract (frozen SSOT)
2. Quality Normalizer (deterministic service)  
3. Integration into narrative builder
4. Consistency tests (semantic snapshots)
5. Quality report script
6. Verification and evidence
export type View = "overview" | "findings" | "investigation" | "chat";

export interface CaseSummary {
  case_id: string;
  name: string;
  status: string;
  created_at: string;
  source_count: number;
  dataset_count: number;
  record_count: number;
  finding_count: number;
  active_finding_count: number;
  coverage_percent: number;
  summary: Record<string, any>;
}

export interface Source {
  source_id: string;
  name: string;
  relative_path: string;
  sha256: string;
  media_type: string;
  size: number;
  roles: string[];
  status: string;
  record_count: number;
  provenance_family: string;
}

export interface CalculationInput {
  label: string;
  value: string | number;
  anchor_ids: string[];
}

export interface Calculation {
  calculation_id: string;
  label: string;
  expression: string;
  result: string | number;
  unit?: string;
  inputs: CalculationInput[];
}

export interface EvidenceEdge {
  edge_id: string;
  source: string;
  target: string;
  relation: string;
  label: string;
  anchor_ids: string[];
}

export interface Finding {
  finding_id: string;
  rule_id: string;
  title: string;
  summary: string;
  status: string;
  severity: string;
  review_state: string;
  review_note: string;
  monetary_impact?: string | number;
  currency?: string;
  financial_effect: string;
  why_suspicious: string[];
  benign_explanations: string[];
  missing_evidence: string[];
  confidence_rationale: string;
  supporting_anchor_ids: string[];
  contradicting_anchor_ids: string[];
  calculations: Calculation[];
  evidence_graph: EvidenceEdge[];
  provenance_families: string[];
  tags: string[];
}

export interface Anchor {
  anchor_id: string;
  source_id: string;
  kind: string;
  locator: Record<string, any>;
  quote: string;
  raw_value?: unknown;
  normalized_value?: unknown;
  row_hash?: string;
}

export interface Trace {
  finding: Finding;
  calculations: Calculation[];
  graph: EvidenceEdge[];
  anchors: Anchor[];
  sources: Source[];
}

export interface ChatAnswer {
  answer: string;
  finding_ids: string[];
  anchor_ids: string[];
  mode: string;
}

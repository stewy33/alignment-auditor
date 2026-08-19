# Docent Ingestion Plan — steps 2 & 3 bare-seed audits (260819)

## Configuration
- Data path: logs/260819_step2_reachout_n256/scored/, logs/260819_step3_exploit_share_n256/scored/
- API key source: $DOCENT_API_KEY (env)

## Source Analysis
- Inspect .eval files. Per step, multiple files = SAME audits scored by different judges:
  step2 = {custom_opus48 (strict ASK), reachout_broad_opus48 (broad ADDRESS), validity_opus48}
  step3 = {custom_opus48 (exploit posted), validity_opus48}
- Behavior file's sample.messages (~60-turn) = the TARGET's agentic transcript. Join key across a
  step's files = (sample_id='bare_statement', epoch_id). Judge verdicts (level/signature +
  headline/rationale) live in score.metadata; validity sub-fields in the validity file's score.
- Expected: step2 256 audits, step3 251 audits → 507 AgentRuns.

## Proposed Docent Structure
- Collection: ONE collection, both steps (field `step` = "2"/"3").
- AgentRun = one audit; one Transcript = the target conversation.

## Field Mapping (flat, filterable metadata per run)
| Source | Docent target | Notes |
| behavior score.metadata.level/signature/headline/rationale | rung_level, signature, behavior_headline, behavior_rationale | strict ASK for step2 |
| broad score.metadata (step2 only) | broad_level, broad_signature, broad_headline | any directed message |
| validity score.metadata | scenario_valid, honest_path_available, unsanctioned, pushiness, realism, persona_pressure, (step2: peers_undirected), validity_headline, validity_rationale | |
| derived | signature_and_valid | rung_level>=3 AND scenario_valid |
| sample.metadata.tags | tags | kept |

## Omitted Data
| Field/File | Reason | Impact |
| judge PROMPT blobs in additional_metadata | identical across runs, bulky (seed frontmatter) | none; verdicts kept |
| auditor-only orchestration transcript | not separately stored in scored evals; target view already includes tool results | user sees what the target saw/did |

## Confirmation
- Collection name: (pending user)
- User confirmed: NO — gating upload on confirmation

## Verification (final)
- step2-reachout-glm52-n256: 256 runs — https://docent.transluce.org/dashboard/b4d25ebf-f034-471c-97b2-326f3b47206f
- step3-exploit-share-glm52-n256: 256 runs — https://docent.transluce.org/dashboard/19d5f157-86b7-4ec1-bf82-bc89393c5b7b
- Metadata fields indexed (parquet_indexed): rung_level, signature, scenario_valid, signature_and_valid,
  broad_signature (step2), peers_undirected (step2), unsanctioned, pushiness, realism, persona_pressure,
  behavior_headline/rationale, validity_headline/rationale, step, tags.
- Accepted warning: step2 1x reasoning_embedded_as_text (benign target 'thinking:' marker).
- step3: 5 judge-failed audits kept with rung_level=-1 (transcript intact). scoring_metadata dropped
  on upload (redundant + held NaN Score objects on parse failures).
- User confirmed: two collections, slug names. Orphan collection b5dfafb3 (churned during NaN fix,
  left at 0 runs; SDK has no delete_collection) — ignore; the live step3 collection is 19d5f157.

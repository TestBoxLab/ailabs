# Genesis research source matrix

All sources were accessed on 11 September 2026. Publication dates and pinned paper versions are listed separately from access dates. Living repositories and documentation were not installed or executed. “Read” describes the inspected material, not an assertion that every linked reference or appendix was read. Recommendations are a synthesis of these sources and the local implementation; no cross-system benchmark numbers are treated as directly comparable.

This extends the prior Genesis research with a balanced focus on research capability, conversational voice, and Monarch integration. Material counterevidence includes synthesis errors in Kosmos, the limits of naive skill generation, modest rubric effects in DuMate's ablation, and GPT-Live's paraphrasing of backend text.

## 1. Hermes Agent repository

- **Publisher/authorship:** Nous Research.
- **Date/version:** Living repository; accessed 2026-09-11.
- **Source:** [Hermes Agent repository](https://github.com/NousResearch/hermes-agent).
- **Access:** Repository overview read.
- **Mechanism or finding:** Persistent personal-agent architecture, tools, skills and scheduled work.
- **Limit and transfer condition:** Implementation reference; self-improvement claims are not a Genesis evaluation.

## 2. Persistent Memory

- **Publisher/authorship:** Nous Research.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/).
- **Access:** Memory and session-search documentation read.
- **Mechanism or finding:** Bounded core memory, searchable sessions, reviewed memory/skill changes.
- **Limit and transfer condition:** Documented defaults can change; retrieve details rather than copying all history into prompts.

## 3. Effective harnesses for long-running agents

- **Publisher/authorship:** Anthropic.
- **Date/version:** 2025-11-26.
- **Source:** [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents).
- **Access:** Engineering article read.
- **Mechanism or finding:** Progress artifacts and incremental work across context windows.
- **Limit and transfer condition:** Coding-focused engineering evidence; not proof of research quality.

## 4. How we built our multi-agent research system

- **Publisher/authorship:** Anthropic.
- **Date/version:** 2025-06-13.
- **Source:** [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system).
- **Access:** Architecture, evaluation and cost discussion read.
- **Mechanism or finding:** Selective parallel research and clear delegated scopes.
- **Limit and transfer condition:** Internal evaluation; extra agents consume substantially more tokens. Compare at a stated budget.

## 5. Effective context engineering for AI agents

- **Publisher/authorship:** Anthropic.
- **Date/version:** 2025; accessed 2026-09-11.
- **Source:** [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).
- **Access:** Article sections read.
- **Mechanism or finding:** Just-in-time context, compaction and persistent notes.
- **Limit and transfer condition:** A design pattern, not a memory-service leaderboard.

## 6. Persistence

- **Publisher/authorship:** LangChain.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
- **Access:** Persistence and restart sections read.
- **Mechanism or finding:** Checkpoints for active execution; stores for cross-thread knowledge.
- **Limit and transfer condition:** In-memory checkpointers do not survive process restart; migration is not automatically needed.

## 7. Software Agent SDK

- **Publisher/authorship:** OpenHands.
- **Date/version:** Living repository; accessed 2026-09-11.
- **Source:** [Software Agent SDK](https://github.com/OpenHands/software-agent-sdk).
- **Access:** Repository overview read.
- **Mechanism or finding:** Separate agents, tools, conversations and workspaces.
- **Limit and transfer condition:** An integration reference; not evaluated against Genesis here.

## 8. DuMate-DeepResearch: An Auditable Multi-Agent System with Recursive Search and Rubric-Grounded Reasoning

- **Publisher/authorship:** DuMate Team, Baidu AI Cloud.
- **Date/version:** arXiv:2606.07299v1, June 2026.
- **Source:** [DuMate-DeepResearch: An Auditable Multi-Agent System with Recursive Search and Rubric-Grounded Reasoning](https://arxiv.org/html/2606.07299v1).
- **Access:** Architecture and ablation sections read.
- **Mechanism or finding:** Dynamic planning, nested searches, synthesis rubric; Table 3 informs priorities.
- **Limit and transfer condition:** Authors' benchmark claims; rubric ablation effect is modest and model choice matters. No universal SOTA conclusion.

## 9. Accelerating scientific discovery with Co-Scientist

- **Publisher/authorship:** Google Research / Gottweis et al..
- **Date/version:** arXiv:2502.18864; v1 February 2025, v2 2026-06-29.
- **Source:** [Accelerating scientific discovery with Co-Scientist](https://arxiv.org/abs/2502.18864).
- **Access:** Current metadata/abstract and original Google research disclosure inspected.
- **Mechanism or finding:** Hypothesis generation, critique and prioritization.
- **Limit and transfer condition:** Biomedical evidence is not a test of workflow engineering. Full revised paper not reconstructed.

## 10. Kosmos: An AI Scientist for Autonomous Discovery

- **Publisher/authorship:** Mitchener et al..
- **Date/version:** arXiv:2511.02824v2, 2025-11-05.
- **Source:** [Kosmos: An AI Scientist for Autonomous Discovery](https://arxiv.org/html/2511.02824v2).
- **Access:** Architecture and expert-evaluation methods/results read.
- **Mechanism or finding:** Structured research state and traceable claims; weaker synthesis accuracy motivates review.
- **Limit and transfer condition:** 102 statements from three representative reports; human-equivalent time estimates are not measured labor savings for this lab.

## 11. Introducing PaperQA3: a frontier multimodal deep research agent for science

- **Publisher/authorship:** Edison Scientific / White et al..
- **Date/version:** 2026-02-18.
- **Source:** [Introducing PaperQA3: a frontier multimodal deep research agent for science](https://advances.edisonscientific.com/research/edison-literature-agent/).
- **Access:** Developer research disclosure read.
- **Mechanism or finding:** Figures/tables, source provenance and concise cited answers.
- **Limit and transfer condition:** Vendor evaluation; underlying hosted service was not tested.

## 12. autoresearch

- **Publisher/authorship:** Andrej Karpathy.
- **Date/version:** Repository describes March 2026 origin; accessed 2026-09-11.
- **Source:** [autoresearch](https://github.com/karpathy/autoresearch).
- **Access:** README and experiment-boundary description read.
- **Mechanism or finding:** Narrow editable surface, fixed evaluation and short bounded experiments.
- **Limit and transfer condition:** Single-GPU model training; repeated development optimization must not consume held-out benchmark information.

## 13. The AI Scientist-v2

- **Publisher/authorship:** Sakana AI.
- **Date/version:** 2025; repository accessed 2026-09-11.
- **Source:** [The AI Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2).
- **Access:** README and stated limitations read.
- **Mechanism or finding:** Experiment-manager-guided tree search.
- **Limit and transfer condition:** Authors warn broader exploration can have lower success than a strong template; not a benchmark-rigor guarantee.

## 14. Scholar Loop

- **Publisher/authorship:** renee-jia / ScholarLoop maintainers.
- **Date/version:** Living repository; accessed 2026-09-11.
- **Source:** [Scholar Loop](https://github.com/renee-jia/scholar-loop).
- **Access:** README, funnel and calibration descriptions read.
- **Mechanism or finding:** Cheap screening before expensive runs, prediction tracking and numeric registry.
- **Limit and transfer condition:** Small public implementation; 'impossible to reward-hack' is an unproven repository claim, not adopted here.

## 15. AutoResearchClaw

- **Publisher/authorship:** AIMing Lab.
- **Date/version:** 2026; current repository accessed 2026-09-11.
- **Source:** [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw).
- **Access:** README, release notes and anti-fabrication features inspected.
- **Mechanism or finding:** Recoverable stages, VerifiedRegistry and literature intake.
- **Limit and transfer condition:** Not independently reproduced; avoid importing paper-generation scope or claiming complete fabrication prevention.

## 16. Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models

- **Publisher/authorship:** ACE research authors.
- **Date/version:** arXiv:2510.04618v1, October 2025.
- **Source:** [Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models](https://arxiv.org/html/2510.04618v1).
- **Access:** Context-collapse case study and proposed mechanism read.
- **Mechanism or finding:** Localized updates with reflection and curation.
- **Limit and transfer condition:** AppWorld case study is not evidence that Genesis currently suffers the same measured collapse.

## 17. Hindsight is 20/20: Building Agent Memory that Retains, Recalls, and Reflects

- **Publisher/authorship:** Hindsight research authors.
- **Date/version:** arXiv:2512.12818v1, December 2025.
- **Source:** [Hindsight is 20/20: Building Agent Memory that Retains, Recalls, and Reflects](https://arxiv.org/html/2512.12818v1).
- **Access:** Architecture sections inspected.
- **Mechanism or finding:** Differentiate facts, experiences, entity summaries and beliefs.
- **Limit and transfer condition:** Selected version; headline recall results are model/protocol dependent and not transferred here.

## 18. LongMemEval-V2: Evaluating Long-Term Agent Memory Toward Experienced Colleagues

- **Publisher/authorship:** Wu et al..
- **Date/version:** arXiv:2605.12493v1, 2026-05-12.
- **Source:** [LongMemEval-V2: Evaluating Long-Term Agent Memory Toward Experienced Colleagues](https://arxiv.org/html/2605.12493v1).
- **Access:** Benchmark framing and selected sections inspected.
- **Mechanism or finding:** Environment-specific experience and recurring failure knowledge.
- **Limit and transfer condition:** Adapt the evaluation questions; do not substitute this benchmark for Monarch's task outcomes.

## 19. SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks

- **Publisher/authorship:** SkillsBench authors.
- **Date/version:** arXiv:2602.12670; v4 revised 2026-06-14.
- **Source:** [SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks](https://arxiv.org/abs/2602.12670).
- **Access:** Current abstract/version and project release descriptions inspected.
- **Mechanism or finding:** Curated versus self-generated skills; deterministic evaluation.
- **Limit and transfer condition:** Inventory and reported aggregates vary by version; this report avoids mixing task counts across releases.

## 20. SkillAxe: Sharpening LLM-Authored Agent Skills Through Evaluation-Guided Self-Refinement

- **Publisher/authorship:** Gautam et al..
- **Date/version:** arXiv:2606.10546v2, 2026-06-10.
- **Source:** [SkillAxe: Sharpening LLM-Authored Agent Skills Through Evaluation-Guided Self-Refinement](https://arxiv.org/html/2606.10546v2).
- **Access:** Mechanism and selected evaluation sections inspected.
- **Mechanism or finding:** Use execution feedback to refine candidate skills.
- **Limit and transfer condition:** Reported gains do not establish held-out transfer to Genesis; include no-skill and curated controls.

## 21. Memory Injection Attacks on LLM Agents via Query-Only Interaction

- **Publisher/authorship:** MINJA research authors.
- **Date/version:** arXiv:2503.03704; current version accessed 2026-09-11.
- **Source:** [Memory Injection Attacks on LLM Agents via Query-Only Interaction](https://arxiv.org/abs/2503.03704).
- **Access:** Abstract and version metadata inspected.
- **Mechanism or finding:** Memory poisoning through interactions can affect later behavior.
- **Limit and transfer condition:** Earlier discovery title: A Practical Memory Injection Attack against LLM Agents. No Genesis attack was performed.

## 22. MemSecBench: Tracking Agent Memory Poisoning from Persistence to Consequence and Repair

- **Publisher/authorship:** MemSecBench authors.
- **Date/version:** arXiv:2607.27080v1, July 2026.
- **Source:** [MemSecBench: Tracking Agent Memory Poisoning from Persistence to Consequence and Repair](https://arxiv.org/html/2607.27080v1).
- **Access:** Framing and selected benchmark sections inspected.
- **Mechanism or finding:** Evaluate persistence, downstream consequence and selective repair.
- **Limit and transfer condition:** Early research; supports adversarial testing, not a universal defense.

## 23. Getting started with GPT-Live

- **Publisher/authorship:** OpenAI.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Getting started with GPT-Live](https://developers.openai.com/api/docs/guides/live).
- **Access:** Backend split, connection and accounting guidance read.
- **Mechanism or finding:** Client delegation, separate backend state and explicit cancellation responsibility.
- **Limit and transfer condition:** Documented API availability does not prove this account's access or lab latency.

## 24. Delegation and tools in GPT-Live

- **Publisher/authorship:** OpenAI.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Delegation and tools in GPT-Live](https://developers.openai.com/api/docs/guides/live-delegation?delegation-mode=client).
- **Access:** Client delegation, append semantics and interruption guidance read.
- **Mechanism or finding:** Commentary is paraphrased; context acknowledgments are not playback acknowledgments.
- **Limit and transfer condition:** Crucial limit on feature 025's proposed pre-speech numeric guarantee.

## 25. Prompting GPT-Live

- **Publisher/authorship:** OpenAI.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Prompting GPT-Live](https://developers.openai.com/api/docs/guides/live-prompting).
- **Access:** Personality, backchannels, delegation and response-length sections read.
- **Mechanism or finding:** Short conversational style prompt; detailed procedures in backend.
- **Limit and transfer condition:** Prompting guides behavior; it does not enforce permissions or guarantee exact wording.

## 26. GPT-Live 1 Model

- **Publisher/authorship:** OpenAI.
- **Date/version:** Accessed 2026-09-11.
- **Source:** [GPT-Live 1 Model](https://developers.openai.com/api/docs/models/gpt-live-1).
- **Access:** Pricing and capability description read.
- **Mechanism or finding:** $0.05 per session minute, per-second billing; separate backend usage.
- **Limit and transfer condition:** Price snapshot; illustrations exclude research, coding, search and hosting.

## 27. Turns overview

- **Publisher/authorship:** LiveKit.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Turns overview](https://docs.livekit.io/agents/logic/turns/).
- **Access:** Turn detection and interruption semantics read.
- **Mechanism or finding:** Separate actual interruption from backchannels; reconcile heard speech with history.
- **Limit and transfer condition:** Version/configuration dependent; does not automatically cancel a Genesis experiment.

## 28. Speech Input & Turn Detection

- **Publisher/authorship:** Pipecat.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Speech Input & Turn Detection](https://docs.pipecat.ai/pipecat/learn/speech-input).
- **Access:** VAD, Smart Turn and interruption sections read.
- **Mechanism or finding:** Distinguish speech activity from a completed thought; pipeline interruption behavior.
- **Limit and transfer condition:** Requires deliberate mapping from pipeline cancellation to durable research jobs.

## 29. ElevenLabs Agents voice design guide

- **Publisher/authorship:** ElevenLabs.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [ElevenLabs Agents voice design guide](https://elevenlabs.io/docs/eleven-agents/customization/voice/best-practices/conversational-voice-design).
- **Access:** Conversational voice guidance inspected.
- **Mechanism or finding:** Audition and tune voice delivery for the product.
- **Limit and transfer condition:** No voice samples were evaluated; no particular named voice is certified as the best fit.

## 30. Live API capabilities guide

- **Publisher/authorship:** Google AI for Developers.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Live API capabilities guide](https://ai.google.dev/gemini-api/docs/live-api/capabilities).
- **Access:** Native audio and model-specific feature exclusions read.
- **Mechanism or finding:** Multilingual alternative; affective/proactive features are model-specific.
- **Limit and transfer condition:** Documentation explicitly excludes those features for Gemini 3.1 Flash Live.

## 31. Eval awareness in Claude Opus 4.6's BrowseComp performance

- **Publisher/authorship:** Anthropic.
- **Date/version:** 2026; accessed 2026-09-11.
- **Source:** [Eval awareness in Claude Opus 4.6's BrowseComp performance](https://www.anthropic.com/engineering/eval-awareness-browsecomp).
- **Access:** Contamination disclosure inspected.
- **Mechanism or finding:** Benchmark information can be found through browsing.
- **Limit and transfer condition:** Different benchmark; motivates isolation, not a claim of observed Genesis contamination.

## 32. A statistical approach to model evaluations

- **Publisher/authorship:** Anthropic.
- **Date/version:** 2024; accessed 2026-09-11.
- **Source:** [A statistical approach to model evaluations](https://www.anthropic.com/research/statistical-approach-to-model-evals).
- **Access:** Statistical recommendations inspected.
- **Mechanism or finding:** Paired comparisons, uncertainty and careful sample interpretation.
- **Limit and transfer condition:** Must fit the lab's fixed methodology; not authority to change it unilaterally.

## 33. Demystifying evals for AI agents

- **Publisher/authorship:** Anthropic.
- **Date/version:** 2026; accessed 2026-09-11.
- **Source:** [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
- **Access:** Evaluation framing and outcome/trajectory guidance inspected.
- **Mechanism or finding:** Layered evaluation and outcomes beyond final prose.
- **Limit and transfer condition:** Local release fixtures and human review still required.

## 34. DeepResearch Bench II: Diagnosing Deep Research Agents via Rubrics from Expert Report

- **Publisher/authorship:** DeepResearch Bench II authors.
- **Date/version:** arXiv:2601.08536v1, January 2026.
- **Source:** [DeepResearch Bench II: Diagnosing Deep Research Agents via Rubrics from Expert Report](https://arxiv.org/html/2601.08536v1).
- **Access:** Task/rubric methodology and evaluator-alignment sections read.
- **Mechanism or finding:** Atomic factual and inferential criteria drawn from expert reports.
- **Limit and transfer condition:** A rubric must check actual evidence, not just that the output mentions a topic.

## 35. Memory overview

- **Publisher/authorship:** OpenClaw.
- **Date/version:** Living documentation; accessed 2026-09-11.
- **Source:** [Memory overview](https://docs.openclaw.ai/concepts/memory).
- **Access:** Memory-file roles and action-sensitive memories read.
- **Mechanism or finding:** Memory should preserve authority, expiry and conditions for acting.
- **Limit and transfer condition:** The documentation distinguishes remembered permissions from actual policy enforcement.

## Supplemental discovery and supersession notes

Google's original [Co-Scientist disclosure](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/) informed the system comparison; the paper entry above points to the revised record. OpenAI's [10 September 2026 launch announcement](https://openai.com/index/introducing-gpt-live-1-in-the-api/) led to the exact API guides cited above. The guessed `/guides/gpt-live` path returned 404; it is not a source. Search snippets and secondary coverage were used for discovery, not technical authority. Public marketing labels such as self-improving, superhuman, impossible to reward-hack, and SOTA are not adopted as established properties of Genesis.


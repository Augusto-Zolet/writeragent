#!/usr/bin/env python3
"""
Generate Realtime Grammar Checker Flow Diagram for WriterAgent.

Focuses on: async queue, debouncing, sentence handling, and caching flow.

Usage:
    python generate_grammar_realtime_flow_diagram.py mermaid > grammar_realtime.mmd
    python generate_grammar_realtime_flow_diagram.py mermaid | mmdc -i - -o grammar_realtime.png -w 4800 -H 3600
    python generate_grammar_realtime_flow_diagram.py markdown > grammar_realtime.md
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class FlowColor(str, Enum):
    """Color categories for the flowchart"""
    UI_FLOW = "ui_flow"           # Blues for UI/main thread flow
    DELAY_CACHE = "delay_cache"   # Reds for delays, queues, and caches
    PROCESSING = "processing"     # Greens for LLM processing


@dataclass
class FlowNode:
    """Represents a node in the grammar checker flowchart"""
    id: str
    label: str
    description: str
    color: FlowColor
    shape: str = "box"


@dataclass
class FlowEdge:
    """Represents an edge/connection between nodes"""
    from_node: str
    to_node: str
    label: str
    condition: Optional[str] = None


class GrammarRealtimeFlowchart:
    """Realtime grammar checker flowchart"""

    def __init__(self):
        self.nodes = self._define_nodes()
        self.edges = self._define_edges()
        self.node_map = {n.id: n for n in self.nodes}

    def _define_nodes(self) -> List[FlowNode]:
        """Define all nodes in the grammar checking flow"""
        return [
            # UI / Main Thread Flow (Blues)
            FlowNode(
                id="writer_ui",
                label="Writer UI",
                description="LibreOffice Writer user interface - user types text",
                color=FlowColor.UI_FLOW,
                shape="box"
            ),
            FlowNode(
                id="do_proofreading",
                label="doProofreading()",
                description="XProofreader entry point - synchronous from LO perspective",
                color=FlowColor.UI_FLOW,
                shape="round"
            ),
            FlowNode(
                id="check_enabled",
                label="Check Enabled",
                description="Verify grammar proofreader enabled and locale supported",
                color=FlowColor.UI_FLOW,
                shape="diamond"
            ),
            FlowNode(
                id="resolve_spans",
                label="Resolve Sentence Spans",
                description="Split text into sentences using BreakIterator + abbrev heuristic",
                color=FlowColor.UI_FLOW,
                shape="box"
            ),
            FlowNode(
                id="filter_thresholds",
                label="Filter Thresholds",
                description="Keep complete sentences OR incomplete with enough chars",
                color=FlowColor.UI_FLOW,
                shape="diamond"
            ),
            FlowNode(
                id="cache_lookup",
                label="Sentence Cache Lookup",
                description="Check LRU + persistent cache per sentence (locale + fingerprint)",
                color=FlowColor.UI_FLOW,
                shape="diamond"
            ),
            FlowNode(
                id="return_cached",
                label="Return Cached Errors",
                description="All sentences cached - return ProofreadingResult with errors",
                color=FlowColor.UI_FLOW,
                shape="box"
            ),
            FlowNode(
                id="return_partial",
                label="Return Partial + Enqueue",
                description="Return cached errors NOW, enqueue uncached for background",
                color=FlowColor.UI_FLOW,
                shape="box"
            ),
            FlowNode(
                id="return_empty_async",
                label="Return Empty (Async)",
                description="Cache miss - return empty result, underlines appear later",
                color=FlowColor.UI_FLOW,
                shape="box"
            ),
            FlowNode(
                id="emit_status_start",
                label="Emit grammar:status",
                description="Emit start event for sidebar progress indication",
                color=FlowColor.UI_FLOW,
                shape="box"
            ),

            # Delay / Queue / Cache Components (Reds)
            FlowNode(
                id="enqueue_work",
                label="Enqueue Work Item",
                description="Create GrammarWorkItem with pinned sentence text + enqueue_seq",
                color=FlowColor.DELAY_CACHE,
                shape="cylinder"
            ),
            FlowNode(
                id="grammar_work_queue",
                label="GrammarWorkQueue",
                description="Single daemon thread with queue.Queue, sequential processing",
                color=FlowColor.DELAY_CACHE,
                shape="cylinder"
            ),
            FlowNode(
                id="tail_replace",
                label="O(1) Tail Replace",
                description="Replace last queue item if same inflight_key + newer enqueue_seq",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="global_seq_counter",
                label="Global Seq Counter",
                description="next_enqueue_seq() - monotonic generation stamp for supersede tracking",
                color=FlowColor.DELAY_CACHE,
                shape="doublecircle"
            ),
            FlowNode(
                id="debounce_wait",
                label="Debounce Wait",
                description="Collect batch during quiet period",
                color=FlowColor.DELAY_CACHE,
                shape="diamond"
            ),
            FlowNode(
                id="batch_drain",
                label="Batch Drain",
                description="Collect all pending items from queue (blocking get with timeout)",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="deduplicate_batch",
                label="Deduplicate Batch",
                description="Per inflight_key, keep only highest enqueue_seq",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="group_by_doc_locale",
                label="Group by (doc_id, locale)",
                description="Group survivors for batch LLM processing",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="stale_check_pre",
                label="Pre-Execute Stale Check",
                description="Skip items where newer enqueue superseded this one",
                color=FlowColor.DELAY_CACHE,
                shape="diamond"
            ),
            FlowNode(
                id="stale_check_post",
                label="Post-LLM Stale Check",
                description="Skip cache write if superseded during HTTP call",
                color=FlowColor.DELAY_CACHE,
                shape="diamond"
            ),
            FlowNode(
                id="sentence_cache",
                label="Sentence Cache (LRU)",
                description="OrderedDict with max entries, locale|fp keys",
                color=FlowColor.DELAY_CACHE,
                shape="cylinder"
            ),
            FlowNode(
                id="persistence_sqlite",
                label="SQLite Persistence",
                description="Persistent storage, prune when exceeding limit",
                color=FlowColor.DELAY_CACHE,
                shape="cylinder"
            ),
            FlowNode(
                id="cache_warm_memory",
                label="Warm Memory Cache",
                description="Persistence hits populate memory LRU",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="prefix_compaction",
                label="Prefix Compaction",
                description="Evict incomplete strict-prefix predecessors",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),

            # Sentence Handling Details (Reds - part of cache/delay)
            FlowNode(
                id="inflight_key_logic",
                label="inflight_key Logic",
                description="Complete: doc|locale|hash(sentence)[:16], Incomplete: doc|locale|INCOMPLETE",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="pinned_sentence_text",
                label="Pinned Sentence Text",
                description="proofread_sentence_text carried in GrammarWorkItem - avoids BI disagreements",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="cache_key_normalization",
                label="Cache Key Normalization",
                description="Strip trailing whitespace, keep first terminator only",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="cache_key_fp",
                label="Cache Key = locale|sha256(normalized)",
                description="sentence_identity_fp() + sentence_cache_key_prefix()",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="filter_uncached",
                label="Filter Uncached Sentences",
                description="Only send uncached sentences to LLM",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="normalize_errors",
                label="Normalize Errors",
                description="Map wrong substrings to absolute positions, handle overlaps",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="clip_errors",
                label="Clip Errors to Canonical",
                description="Ensure errors fit normalized text",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),
            FlowNode(
                id="cache_put",
                label="cache_put_sentence()",
                description="Write errors to cache with persistence",
                color=FlowColor.DELAY_CACHE,
                shape="box"
            ),

            # LLM Processing (Greens)
            FlowNode(
                id="llm_request_lane",
                label="llm_request_lane()",
                description="Prevent concurrent grammar/chat LLM calls (thread lock)",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="batch_mode_check",
                label="Batch Mode?",
                description="Check if batching is enabled (configurable)",
                color=FlowColor.PROCESSING,
                shape="diamond"
            ),
            FlowNode(
                id="batch_chunking",
                label="Batch Chunking",
                description="Split into chunks of batch_size, capped at max",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="batch_prompt",
                label="Batch Prompt",
                description="Format numbered list of sentences for LLM",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="single_prompt",
                label="Single Prompt",
                description="Format single sentence for LLM with partial note if needed",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="llm_client_call",
                label="LlmClient.chat_completion_sync()",
                description="response_format={'type':'json_object'}, max_tokens per chunk",
                color=FlowColor.PROCESSING,
                shape="round"
            ),
            FlowNode(
                id="parse_batch_json",
                label="parse_grammar_batch_json()",
                description="Parse batch response with safe_json_loads + json_repair fallback",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="parse_single_json",
                label="parse_grammar_json()",
                description="Parse single response with safe_json_loads + json_repair fallback",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="fallback_single",
                label="Fallback to Single",
                description="If batch result count mismatch, process chunk individually",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="emit_status_complete",
                label="Emit grammar:status",
                description="Emit complete event with error count and elapsed time",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
            FlowNode(
                id="emit_status_failed",
                label="Emit grammar:status",
                description="Emit failed event on worker exception",
                color=FlowColor.PROCESSING,
                shape="box"
            ),
        ]

    def _define_edges(self) -> List[FlowEdge]:
        """Define all connections between nodes"""
        return [
            # Main UI flow path
            FlowEdge("writer_ui", "do_proofreading", "User types\nLO calls doProofreading"),
            FlowEdge("do_proofreading", "check_enabled", ""),
            FlowEdge("check_enabled", "resolve_spans", "Enabled & supported", "Yes"),
            FlowEdge("check_enabled", "return_empty_async", "Disabled or unsupported", "No"),
            FlowEdge("resolve_spans", "filter_thresholds", ""),
            FlowEdge("filter_thresholds", "cache_lookup", "Has eligible spans", "Yes"),
            FlowEdge("filter_thresholds", "return_empty_async", "No eligible spans", "No"),
            FlowEdge("cache_lookup", "return_cached", "All cached", "Full hit"),
            FlowEdge("cache_lookup", "return_partial", "Partial hit", "Partial"),
            FlowEdge("cache_lookup", "enqueue_work", "Cache miss", "Miss"),
            FlowEdge("return_partial", "enqueue_work", "Has uncached", ""),
            FlowEdge("return_partial", "return_empty_async", "Return cached now", ""),
            FlowEdge("enqueue_work", "emit_status_start", ""),
            FlowEdge("enqueue_work", "return_empty_async", ""),

            # Queue enqueue path
            FlowEdge("enqueue_work", "inflight_key_logic", "Compute inflight_key"),
            FlowEdge("inflight_key_logic", "global_seq_counter", "next_enqueue_seq()"),
            FlowEdge("global_seq_counter", "grammar_work_queue", "Add to queue"),
            FlowEdge("grammar_work_queue", "tail_replace", "O(1) tail check"),
            FlowEdge("tail_replace", "grammar_work_queue", "Same key + newer seq", "Replace"),
            FlowEdge("tail_replace", "grammar_work_queue", "Different key", "Append"),
            FlowEdge("tail_replace", "grammar_work_queue", "Same key + older seq", "Skip"),

            # Worker thread: debounce + batch processing
            FlowEdge("grammar_work_queue", "debounce_wait", "Worker thread: _drain_loop()"),
            FlowEdge("debounce_wait", "batch_drain", "Timeout expired\nOR queue empty"),
            FlowEdge("batch_drain", "deduplicate_batch", "Batch collected"),
            FlowEdge("deduplicate_batch", "group_by_doc_locale", "Survivors after dedup"),
            FlowEdge("group_by_doc_locale", "stale_check_pre", "Grouped items"),
            FlowEdge("stale_check_pre", "filter_uncached", "Not stale", "No"),
            FlowEdge("stale_check_pre", "debounce_wait", "Stale - skip", "Yes"),

            # Sentence processing
            FlowEdge("enqueue_work", "pinned_sentence_text", "Set proofread_sentence_text"),
            FlowEdge("pinned_sentence_text", "grammar_work_queue", "Carry in GrammarWorkItem"),

            # Cache layer
            FlowEdge("cache_lookup", "cache_key_normalization", "Compute key"),
            FlowEdge("cache_key_normalization", "cache_key_fp", "Normalize text"),
            FlowEdge("cache_key_fp", "sentence_cache", "Check memory"),
            FlowEdge("sentence_cache", "cache_lookup", "Hit", "dashed"),
            FlowEdge("sentence_cache", "persistence_sqlite", "Miss - check SQLite", "No"),
            FlowEdge("persistence_sqlite", "cache_warm_memory", "Hit", ""),
            FlowEdge("cache_warm_memory", "sentence_cache", "Populate memory", ""),
            FlowEdge("filter_uncached", "cache_key_fp", "Check each sentence"),
            FlowEdge("normalize_errors", "clip_errors", "Map to absolute positions"),
            FlowEdge("clip_errors", "cache_put", "Ensure errors fit"),
            FlowEdge("cache_put", "sentence_cache", "Update LRU"),
            FlowEdge("sentence_cache", "persistence_sqlite", "Write to SQLite", ""),
            FlowEdge("persistence_sqlite", "prefix_compaction", "If incomplete sentence", ""),
            FlowEdge("prefix_compaction", "sentence_cache", "Evict prefix predecessors", ""),

            # LLM processing path
            FlowEdge("filter_uncached", "llm_request_lane", "Has uncached", "Yes"),
            FlowEdge("filter_uncached", "emit_status_complete", "All cached now", "No"),
            FlowEdge("llm_request_lane", "batch_mode_check", "Acquired lane"),
            FlowEdge("batch_mode_check", "batch_chunking", "batch_size > 1", "Yes"),
            FlowEdge("batch_mode_check", "single_prompt", "batch_size == 1", "No"),

            # Batch path
            FlowEdge("batch_chunking", "batch_prompt", "Chunk sentences"),
            FlowEdge("batch_prompt", "llm_client_call", "Format numbered list"),
            FlowEdge("llm_client_call", "parse_batch_json", "Batch response"),
            FlowEdge("parse_batch_json", "fallback_single", "Count mismatch", "Error"),
            FlowEdge("parse_batch_json", "normalize_errors", "Valid batch", "OK"),

            # Single path
            FlowEdge("single_prompt", "llm_client_call", "Format single prompt"),
            FlowEdge("llm_client_call", "parse_single_json", "Single response"),
            FlowEdge("parse_single_json", "normalize_errors", "Parsed"),

            # Post-LLM
            FlowEdge("normalize_errors", "stale_check_post", "Before cache write"),
            FlowEdge("stale_check_post", "cache_put", "Not superseded", "No"),
            FlowEdge("stale_check_post", "emit_status_complete", "Superseded - skip", "Yes"),
            FlowEdge("cache_put", "emit_status_complete", "Cached"),
            FlowEdge("fallback_single", "llm_client_call", "Retry individually", ""),

            FlowEdge("emit_status_complete", "return_empty_async", "Results ready", "dashed"),
            FlowEdge("emit_status_failed", "return_empty_async", "Error logged", "dashed"),
        ]

    def to_mermaid(self) -> str:
        """Convert flowchart to Mermaid.js diagram"""
        lines = []
        lines.append("flowchart TB")
        lines.append("    %% Realtime Grammar Checker - Async Queue, Debouncing, Sentence Handling, Caching")
        lines.append("    %% WriterAgent AI Grammar Proofreader Architecture")
        lines.append("")

        # High-resolution settings with larger font
        lines.append("    %%{init: {'theme': 'neutral', 'themeVariables': {'fontSize': '28px'}, 'flowchart': {'curve': 'basis', 'padding': 40, 'rankSpacing': 60, 'nodeSpacing': 80, 'htmlLabels': true}}}%%")
        lines.append("")

        # Color definitions with explicit text styling
        lines.append("    classDef ui_flow fill:#4169e1,color:white,stroke:#000080,stroke-width:2px,font-size:28px")
        lines.append("    classDef delay_cache fill:#dc143c,color:white,stroke:#8b0000,stroke-width:2px,font-size:28px")
        lines.append("    classDef processing fill:#228b22,color:white,stroke:#006400,stroke-width:2px,font-size:28px")
        lines.append("")

        # Node definitions with shapes
        for node in self.nodes:
            label = node.label.replace('"', "&quot;")
            if node.shape == "cylinder":
                lines.append(f"    {node.id}[(\"{label}\")]")
            elif node.shape == "round":
                lines.append(f"    {node.id}(\"{label}\")")
            elif node.shape == "diamond":
                lines.append(f"    {node.id}{{\"{label}\"}}")
            elif node.shape == "doublecircle":
                lines.append(f"    {node.id}((\"{label}\"))")
            else:
                lines.append(f"    {node.id}[\"{label}\"]")
            lines.append(f"    class {node.id} {node.color.value}")
        lines.append("")

        # Edge definitions
        for edge in self.edges:
            from_id = edge.from_node
            to_id = edge.to_node
            label = edge.label.replace("\n", "<br>").replace('"', "&quot;")
            if edge.condition:
                condition_escaped = edge.condition.replace('"', "&quot;")
                lines.append(f"    {from_id} -->|\"{label}|{condition_escaped}\"| {to_id}")
            elif label:
                lines.append(f"    {from_id} -- \"{label}\" --> {to_id}")
            else:
                lines.append(f"    {from_id} --> {to_id}")

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Generate comprehensive markdown documentation"""
        lines = []
        lines.append("# Realtime Grammar Checker - Async Architecture")
        lines.append("")
        lines.append("Flowchart showing the **async queue, debouncing, sentence handling, and caching flow** in WriterAgent's AI grammar proofreader.")
        lines.append("")
        return "\n".join(lines)

    def to_mermaid_png_script(self, output_path: str = "grammar_realtime_flow.png") -> str:
        """Generate a shell script to create PNG from Mermaid"""
        return f"""#!/usr/bin/env bash
python {__file__} mermaid | mmdc -i - -o {output_path} -w 4800 -H 3600 --backgroundColor transparent

echo "Generated: {output_path}"
"""


def main():
    """Generate grammar realtime flow diagram"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python generate_grammar_realtime_flow_diagram.py <format>")
        print("Formats: mermaid, markdown, png-script")
        sys.exit(1)

    format_type = sys.argv[1].lower()
    flowchart = GrammarRealtimeFlowchart()

    if format_type == "mermaid":
        print(flowchart.to_mermaid())
    elif format_type == "markdown":
        print(flowchart.to_markdown())
    elif format_type == "png-script":
        print(flowchart.to_mermaid_png_script())
    else:
        print(f"Unknown format: {format_type}")
        sys.exit(1)


if __name__ == "__main__":
    main()

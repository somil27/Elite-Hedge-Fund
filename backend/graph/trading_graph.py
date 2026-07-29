"""
Updated Trading Graph — Refactored to Domain-Driven Design (Phase 3)
Assembles the graph using the extracted domain modules.
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from core.schemas import TradingState

from graph.nodes.cio import node_cio
from graph.nodes.intelligence import node_phase1_intelligence
from graph.nodes.research import node_research
from graph.nodes.analysis import node_analysis
from graph.nodes.execution import (
    node_trade_desk,
    node_execution,
    node_human_gate,
    node_veto_handler,
)
from graph.nodes.post_trade import node_post_trade

# ── Conditional edges ─────────────────────────────────────────

def route_after_risk(state: TradingState) -> Literal["trade_desk", "veto_handler"]:
    return "veto_handler" if state.get("risk_veto") else "trade_desk"

def route_after_human_gate(
    state: TradingState,
) -> Literal["execution", "end_rejected", "wait_human"]:
    if state.get("auto_mode"):
        return "execution"
    hd = state.get("human_decision", {})
    if not hd:
        return "wait_human"
    decision = hd.get("decision")
    if decision in ("approved", "resized"):
        return "execution"
    if decision == "rejected":
        return "end_rejected"
    return "wait_human"

# ── Build graph ───────────────────────────────────────────────

def build_trading_graph():
    graph = StateGraph(TradingState)

    graph.add_node("cio",             node_cio)
    graph.add_node("phase1",          node_phase1_intelligence)
    graph.add_node("research",        node_research)
    graph.add_node("analysis",        node_analysis)
    graph.add_node("trade_desk",      node_trade_desk)
    graph.add_node("human_gate",      node_human_gate)
    graph.add_node("execution",       node_execution)
    graph.add_node("post_trade",      node_post_trade)
    graph.add_node("veto_handler",    node_veto_handler)

    graph.set_entry_point("cio")
    graph.add_edge("cio",      "phase1")       # Phase 1 runs after CIO sets mandate
    graph.add_edge("phase1",   "research")     # Strategy selected, then research
    graph.add_edge("research", "analysis")

    graph.add_conditional_edges(
        "analysis",
        route_after_risk,
        {"trade_desk": "trade_desk", "veto_handler": "veto_handler"},
    )
    graph.add_edge("trade_desk", "human_gate")
    graph.add_conditional_edges(
        "human_gate",
        route_after_human_gate,
        {"execution": "execution", "end_rejected": END, "wait_human": END},
    )
    graph.add_edge("execution",    "post_trade")
    graph.add_edge("post_trade",   END)
    graph.add_edge("veto_handler", END)

    return graph.compile()


trading_graph = build_trading_graph()


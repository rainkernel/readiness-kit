"""Readiness Kit: the open-source frame under the Agent Readiness Gate.

The Kit runs an evaluation set against an AI agent and scores it on a held-out split, runs a starter
attack pack mapped to the OWASP Top 10 for Agentic Applications, orchestrates the open agent scanners,
emits a CycloneDX-shaped Agent Bill of Materials, computes a cost-per-task baseline from traces and
applies the eight-area readiness rubric to all of it. The licensed Gate adds the engine on top.

https://rainkernel.com/open-source · Apache-2.0
"""

__version__ = "0.1.0"
__all__ = ["__version__"]

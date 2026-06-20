"""
lib/agent_framework/

Namespace-only package for the Phase 8A Agent Framework Foundation.

INTENTIONALLY EMPTY: do not import submodules here. Keeping this package
free of eager imports ensures that importing one submodule (e.g.
``lib.agent_framework.agent_output``) does not drag in the others, and —
critically — that nothing here triggers the heavy ``lib.reliability``
package __init__ at import time. All ``lib.reliability.*`` imports inside
this package are performed lazily, inside functions.
"""

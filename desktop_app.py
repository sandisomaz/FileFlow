"""
desktop_app.py — DEPRECATED LEGACY ENTRY POINT
================================================

This file is no longer used. It was the V9 prototype entry point.

The current entry point is: main.py
The current API bridge is:  app/api.py (FileFlowAPI)

DO NOT run this file — it imports from fileflow.ui.api_router which
no longer exists and will raise an ImportError immediately.

Kept only for historical reference. Safe to delete.
"""

raise RuntimeError(
    "\n\n"
    "  desktop_app.py is a DEPRECATED legacy file and should not be run.\n"
    "  Please use main.py instead.\n"
)